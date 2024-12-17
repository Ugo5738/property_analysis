import ssl

import aiohttp
import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from decouple import config
from django.conf import settings

from accounts.models import UserToken
from analysis.models import (
    AnalysisTask,
    GroupedImages,
    MergedPropertyImage,
    Property,
    PropertyImage,
)
from property_analysis.config.logging_config import configure_logger
from utils.image_processing import download_images
from utils.openai_analysis import get_openai_chat_response
from utils.property_analysis import process_property

logger = configure_logger(__name__)


@shared_task()
# @shared_task(name="property_analysis.tasks.analyze_property", queue="analysis_queue")
def analyze_property(property_id, task_id, phone_number, job_id, source="frontend"):
    logger.info("Starting analyze_property task...")
    async_to_sync(analyze_property_async)(
        property_id, task_id, phone_number, job_id, source
    )


async def analyze_property_async(property_id, task_id, phone_number, job_id, source):
    logger.info("Analyze Property initiated...")
    channel_layer = get_channel_layer()
    logger.info(f"Channel layer obtained: {channel_layer}")

    logger.info(
        f"Fetching property with ID {property_id} and phone number {phone_number}"
    )
    property_instance = await Property.objects.aget(
        id=property_id, phone_number=phone_number
    )
    user_token_obj = await UserToken.objects.aget(phone_number=phone_number)
    user_token = user_token_obj.token

    logger.info(f"Property instance retrieved: {property_instance}")

    logger.info(f"Fetching analysis task with ID {task_id}")
    task_instance = await AnalysisTask.objects.aget(id=task_id)
    logger.info(f"Task instance retrieved: {task_instance}")

    # await sync_to_async(clear_property_data)(property_instance)

    async def update_progress(stage, message, progress):
        logger.info(
            f"Updating progress: Stage={stage}, Message={message}, Progress={progress}%"
        )
        task_instance.status = stage
        task_instance.progress = progress
        task_instance.stage = stage
        task_instance.stage_progress[stage] = progress
        await task_instance.asave()
        logger.info("Task instance progress updated and saved.")

        if source == "frontend":
            logger.info(
                f"Sending progress update via WebSocket to analysis_{phone_number}"
            )
            # Send progress update via WebSocket
            await channel_layer.group_send(
                f"analysis_{phone_number}",
                {
                    "type": "analysis_progress",
                    "message": {
                        "stage": stage,
                        "message": message,
                        "progress": progress,
                    },
                },
            )
        elif source == "whatsapp":
            logger.info("Sending progress update via WhatsApp")
            # Send progress update via WhatsApp
            progress_message = (
                f"Stage: {stage}\nProgress: {progress}%\nMessage: {message}"
            )
            # send_whatsapp_message(phone_number, progress_message)

    try:
        # Download images
        logger.info("Starting image download...")
        await update_progress("download", "Downloading images", 0)

        # Retrieve scraped data from scraper app
        django_settings_module = config("DJANGO_SETTINGS_MODULE")
        logger.info(f"Current DJANGO_SETTINGS_MODULE: {django_settings_module}")

        if django_settings_module == "property_analysis.settings.staging":
            logger.info("Environment: Staging")
            async with aiohttp.ClientSession() as session:
                url = f"http://analysis-scraper-app:8001/api/site-scrapers/scrape/{job_id}/data/"
                logger.info(f"Fetching scraped data from URL: {url}")
                async with session.get(url, timeout=10) as response:
                    logger.info(f"Response status: {response.status}")
                    if response.status != 200:
                        raise Exception(
                            f"Failed to retrieve scraped data. Status code: {response.status}"
                        )
                    scraped_data = await response.json()
                    logger.info(f"Scraped data received: {scraped_data}")
                    scraped_data = scraped_data.get("data")
        elif django_settings_module == "property_analysis.settings.prod_with_raw_ip":
            logger.info("Environment: Production with raw IP")
            # Create an SSL context that does not verify certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession() as session:
                url = f"https://{settings.SCRAPER_APP_URL}/api/site-scrapers/scrape/{job_id}/data/"
                logger.info(f"Fetching scraped data from URL: {url}")
                async with session.get(url, timeout=10, ssl=ssl_context) as response:
                    logger.info(f"Response status: {response.status}")
                    if response.status != 200:
                        raise Exception(
                            f"Failed to retrieve scraped data. Status code: {response.status}"
                        )
                    scraped_data = await response.json()
                    logger.info(f"Scraped data received: {scraped_data}")
                    scraped_data = scraped_data.get("data")
        elif django_settings_module == "property_analysis.settings.prod":
            logger.info("Environment: Production")
            async with aiohttp.ClientSession() as session:
                url = f"https://{settings.SCRAPER_APP_URL}/api/site-scrapers/scrape/{job_id}/data/"
                logger.info(f"Fetching scraped data from URL: {url}")
                async with session.get(url, timeout=10) as response:
                    logger.info(f"Response status: {response.status}")
                    if response.status != 200:
                        raise Exception(
                            f"Failed to retrieve scraped data. Status code: {response.status}"
                        )
                    scraped_data = await response.json()
                    logger.info(f"Scraped data received: {scraped_data}")
                    scraped_data = scraped_data.get("data")
        else:
            logger.info("Unknown DJANGO_SETTINGS_MODULE value.")
            raise Exception("Invalid DJANGO_SETTINGS_MODULE configuration.")

        if not scraped_data:
            logger.info("No scraped data received from scraper app.")
            await update_progress("error", "No data received from scraper app.", 0)
            return
        else:
            logger.info(f"Scraped data: {scraped_data}")

        # Save scraped data to your main app's database
        logger.info("Saving scraped data to the database...")
        property_instance.address = scraped_data.get("address")
        property_instance.price = scraped_data.get("price")
        property_instance.bedrooms = scraped_data.get("bedrooms")
        property_instance.bathrooms = scraped_data.get("bathrooms")
        property_instance.size = scraped_data.get("size")
        property_instance.house_type = scraped_data.get("house_type")
        property_instance.agent = scraped_data.get("agent")
        property_instance.description = scraped_data.get("description")
        property_instance.time_on_market = scraped_data.get("time_on_market")
        property_instance.features = scraped_data.get("features")
        property_instance.listing_type = scraped_data.get("listing_type")
        property_instance.image_urls = scraped_data.get("images")
        property_instance.floorplan_urls = scraped_data.get("floorplans")
        await property_instance.asave()
        logger.info("Property instance updated and saved.")

        # Process description and features using the grok function to create reviewed_description
        logger.info("Processing property description and features...")
        instruction = (
            "Please improve and summarize the following property description and key features, "
            "and produce a reviewed description suitable for property buyers."
        )
        message = f"Description: {property_instance.description}\nFeatures: {property_instance.features}"
        logger.info(f"Instruction: {instruction}")
        logger.info(f"Message for OpenAI API: {message}")

        prompt_format = {
            "type": "object",
            "properties": {
                "reviewed_description": {"type": "string"},
            },
            "required": ["reviewed_description"],
            "additionalProperties": False,
        }
        logger.info(f"Prompt format: {prompt_format}")

        review_data = "Property instance saved."
        try:
            reviewed_data = get_openai_chat_response(
                instruction, message, prompt_format
            )
            logger.info(f"Received reviewed data: {reviewed_data}")
            property_instance.reviewed_description = reviewed_data[
                "reviewed_description"
            ]
            review_data = review_data + "with reviewed description."
        except Exception as e:
            logger.info(f"Failed to get reviewed description: {e}")
            # Proceed without the reviewed description
            property_instance.reviewed_description = None
            # Optionally, schedule a retry or log the error
        finally:
            await property_instance.asave()
            logger.info(review_data)

        logger.info("Downloading images...")
        image_ids, failed_downloads = await download_images(
            property_instance, update_progress
        )
        logger.info(f"Image IDs obtained: {image_ids}")
        logger.info(f"Failed image downloads: {failed_downloads}")
        property_instance.failed_downloads = failed_downloads

        # Process property
        logger.info("Processing property analysis...")
        result = await process_property(
            property_instance.url, image_ids, update_progress, phone_number
        )
        # logger.info(f"Property analysis result: {result}")
        logger.info(f"Property analysis done")

        # Update property with results
        logger.info("Updating property with analysis results...")
        property_instance.overall_condition = result["Condition"]
        property_instance.detailed_analysis = result["Detailed Analysis"]
        property_instance.overall_analysis = result["Overall Analysis"]
        await property_instance.asave()
        logger.info("Property instance saved with analysis results.")

        logger.info("Updating task status to COMPLETED.")
        task_instance.status = "COMPLETED"
        task_instance.progress = 100.0
        await task_instance.asave()
        logger.info("Task instance updated and saved.")

        await update_progress("complete", "Analysis completed successfully", 100.0)
        logger.info("Analysis completed successfully.")

        # Send final results
        if source == "whatsapp":
            logger.info("Sending final results via WhatsApp...")
            # Format the final results message
            final_message = f"Your property analysis is complete.\nOverall Condition: {result['Condition']['overall_condition_label']}\nAverage Score: {result['Condition']['average_score']}\n\nThank you for using our service!"
            logger.info(f"Final message: {final_message}")
            notify_user(phone_number, user_token, property_id, result)
        else:
            logger.info("Final results will be sent via WebSockets and whatsapp.")
            notify_user(phone_number, user_token, property_id, result)
    except Exception as e:
        logger.info(f"An error occurred: {str(e)}")
        await update_progress("error", f"Error during analysis: {str(e)}", 0.0)
        if source == "whatsapp":
            logger.info("Sending error message via WhatsApp.")
            # send_whatsapp_message(phone_number, f"An error occurred during analysis: {str(e)}")
            pass
        task_instance.status = "ERROR"
        await task_instance.asave()
        property_instance.overall_condition = {"error": str(e)}
        await property_instance.asave()
        logger.info("Error handling completed.")


def clear_property_data(property_instance):
    # Delete associated PropertyImage objects
    PropertyImage.objects.filter(property=property_instance).delete()

    # Delete associated GroupedImages objects
    GroupedImages.objects.filter(property=property_instance).delete()

    # Delete associated MergedPropertyImage objects
    MergedPropertyImage.objects.filter(property=property_instance).delete()

    # Delete associated AnalysisTask objects
    AnalysisTask.objects.filter(property=property_instance).delete()

    # Clear analysis results and reset fields
    property_instance.overall_condition = None
    property_instance.detailed_analysis = None
    property_instance.failed_downloads = []
    property_instance.image_urls = []
    property_instance.save()


def notify_user(phone_number, user_token, property_id, analysis_data):
    # This function is called once analysis is complete
    notification_service_url = f"{settings.NOTIFICATION_APP}/api/notifications/notify/"

    analysis_url = (
        f"{settings.FRONTEND_APP}/property-analysis/{property_id}/?token={user_token}"
    )

    data = {
        "recipient": phone_number,
        "channel_type": "whatsapp",
        "template_name": "property_analysis_complete",
        "context": {
            "analysis_url": analysis_url,
            "analysis_data": analysis_data,
            # more data here if necessary
        },
    }

    try:
        response = requests.post(notification_service_url, json=data, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        # Handle exceptions or retry
        pass


{
    "property_url": "https://www.rightmove.co.uk/properties/146759381",
    "stages": {
        "initial_categorization": [
            {"category": "internal", "details": {"room_type": "kitchen"}},
            {"category": "internal", "details": {"room_type": "bedroom"}},
            {"category": "internal", "details": {"room_type": "living room"}},
            {"category": "external", "details": {"exterior_type": "balcony"}},
            {"category": "internal", "details": {"room_type": "master bathroom"}},
            {"category": "internal", "details": {"room_type": "guest bedroom"}},
            {"category": "external", "details": {"exterior_type": "other"}},
            {"category": "internal", "details": {"room_type": "bathroom"}},
            {"category": "internal", "details": {"room_type": "living room"}},
            {"category": "external", "details": {"exterior_type": "neighborhood"}},
        ],
        "grouped_images": {
            "internal": {
                "kitchen_space": [1],
                "bedroom_space": [2, 6],
                "living_space": [3, 9],
                "bathroom_space": [5, 8],
            },
            "external": {"front_garden_space": [4, 7, 10]},
        },
        "merged_images": {
            "internal_kitchen_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_1_Ipj6RXv.jpg"
            ],
            "internal_bedroom_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_2_q6Lzo9B.jpg"
            ],
            "internal_living_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_3_ldB8UNx.jpg"
            ],
            "external_front_garden_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_4_Qzn3iVe.jpg"
            ],
            "internal_bathroom_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_5_hLMzUmh.jpg"
            ],
        },
        "detailed_analysis": {
            "internal_kitchen_space": [
                {
                    "image_number": 1,
                    "condition_label": "Excellent",
                    "reasoning": "The kitchen features high-end, modern finishes and fixtures, with a sleek design and impeccable staging. The cohesive color scheme and bright presentation suggest an excellent condition.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_0_vBoTjSJ.jpg",
                    "image_id": 1,
                    "similarities": {
                        "poor": 0.788019910031569,
                        "above_average": 0.8397828769989097,
                        "below_average": 0.8510994060551111,
                        "excellent": 0.8644751694321945,
                    },
                }
            ],
            "internal_bedroom_space": [
                {
                    "image_number": 1,
                    "condition_label": "Excellent",
                    "reasoning": "The room appears to be newly refurbished with modern furniture, a cohesive design, and a clean presentation. The large mirrored wardrobe and neutral color scheme contribute to the high-end feel.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_1_LY1VOZt.jpg",
                    "image_id": 2,
                    "similarities": {
                        "above_average": 0.8705994753723505,
                        "below_average": 0.8367324696245676,
                        "excellent": 0.8549990130109195,
                        "poor": 0.7822495579066492,
                    },
                },
                {
                    "image_number": 2,
                    "condition_label": "Above Average",
                    "reasoning": "The room is well-presented and clean, with a neutral color scheme and ample natural light. However, it lacks furniture and decor, which makes it less inviting and stylish compared to the Excellent category.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_5_s31NAbM.jpg",
                    "image_id": 6,
                    "similarities": {
                        "above_average": 0.8436932680445176,
                        "below_average": 0.8088104820156155,
                        "excellent": 0.7573051124512092,
                        "poor": 0.8071351835975034,
                    },
                },
            ],
            "internal_living_space": [
                {
                    "image_number": 1,
                    "condition_label": "Excellent",
                    "reasoning": "The space is new and very well-refurbished with a high-end, modern finish. The furniture is stylish and contemporary, and the room has a cohesive design. The presentation is impeccable, matching the standards of a show home.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_2_myn5uQA.jpg",
                    "image_id": 3,
                    "similarities": {
                        "poor": 0.8290703916161166,
                        "above_average": 0.8520500240303333,
                        "below_average": 0.8746171735962347,
                        "excellent": 0.8800696545342208,
                    },
                },
                {
                    "image_number": 2,
                    "condition_label": "Excellent",
                    "reasoning": "This room features high-quality materials, modern furnishings, and a cohesive decor with attention to detail. The presentation is impeccable with a bright, airy atmosphere enhanced by good natural lighting, meeting the criteria for excellence.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_8_Ip1JWa3.jpg",
                    "image_id": 9,
                    "similarities": {
                        "poor": 0.7635194461068455,
                        "above_average": 0.8032604204483211,
                        "below_average": 0.8058883394713208,
                        "excellent": 0.8422207050235084,
                    },
                },
            ],
            "external_front_garden_space": [
                {
                    "image_number": 1,
                    "condition_label": "Excellent",
                    "reasoning": "The exterior space is impeccably maintained with high-quality finishes. The balcony features stylish furniture and a beautiful view, indicative of a carefully curated and cohesive design.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_3_gAUnVGX.jpg",
                    "image_id": 4,
                    "similarities": {
                        "above_average": 0.691769454432527,
                        "below_average": 0.6588049612303928,
                        "excellent": 0.6811463126466217,
                        "poor": 0.6335610979692958,
                    },
                },
                {
                    "image_number": 2,
                    "condition_label": "Above Average",
                    "reasoning": "The building appears well-maintained with some modern finishes. However, the overall setting lacks the high-end features and meticulous attention to detail seen in an 'Excellent' category.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_6_Q5WQKN9.jpg",
                    "image_id": 7,
                    "similarities": {
                        "above_average": 0.7222850364561122,
                        "below_average": 0.7080352111563168,
                        "excellent": 0.7618229421832505,
                        "poor": 0.7256076322396752,
                    },
                },
                {
                    "image_number": 3,
                    "condition_label": "Above Average",
                    "reasoning": "The exterior space has a tidy and maintained appearance with some landscaped elements. The design is attractive but lacks the distinctive features of an 'Excellent' rated space.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_9_WxjAppe.jpg",
                    "image_id": 10,
                    "similarities": {
                        "above_average": 0.6276789102724637,
                        "below_average": 0.60122656704489,
                        "excellent": 0.6875398556606297,
                        "poor": 0.6438176032270172,
                    },
                },
            ],
            "internal_bathroom_space": [
                {
                    "image_number": 1,
                    "condition_label": "Excellent",
                    "reasoning": "The bathroom features modern fixtures, high-quality finishes, and a sleek, contemporary design. The space is well-maintained, with a cohesive color scheme and a clean, impeccable presentation.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_4_AnGp1sI.jpg",
                    "image_id": 5,
                    "similarities": {
                        "above_average": 0.8548060581058172,
                        "below_average": 0.8391028783028338,
                        "excellent": 0.8475050993429631,
                        "poor": 0.8238536004443024,
                    },
                },
                {
                    "image_number": 2,
                    "condition_label": "Excellent",
                    "reasoning": "This image shows a bathroom with modern finishes, stylish fixtures, and a well-proportioned layout. The space is well-lit, with a cohesive, contemporary design and immaculate presentation.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_7_9zmNY9n.jpg",
                    "image_id": 8,
                    "similarities": {
                        "above_average": 0.8560211801849688,
                        "below_average": 0.8175661678896685,
                        "excellent": 0.8327170790304153,
                        "poor": 0.8184424021510757,
                    },
                },
            ],
        },
        "overall_condition": {
            "overall_condition_label": "Excellent",
            "average_score": 4.7,
            "distribution": {"Above Average": 0.3, "Excellent": 0.7},
            "condition_distribution": {"Above Average": 30.0, "Excellent": 70.0},
            "areas_of_concern": 0,
            "confidence": "Low",
            "explanation": "\nDetailed calculation of overall property condition:\n\n1. Total number of valid assessments: 10\n\n2. Condition counts:\n   - Above Average: 3\n   - Excellent: 7\n\n3. Calculation of average score:\n   - Each condition is assigned a value: Excellent (5), Above Average (4), Average (3), Below Average (2), Poor (1)\n   - Total value: 47 (sum of all condition values)\n   - Average score: 47 / 10 = 4.70\n\n4. Distribution of conditions:\n   - Above Average: 30.00%\n   - Excellent: 70.00%\n\n5. Areas of concern (conditions below average): 0\n\n6. Overall rating determination:\n   - Excellent: 4.5 and above\n   - Good: 3.5 to 4.49\n   - Average: 2.5 to 3.49\n   - Below Average: 1.5 to 2.49\n   - Poor: Below 1.5\n\n   Based on the average score of 4.70, the overall rating is: Excellent\n\n7. Confidence level:\n   - High: More than 20 assessments\n   - Medium: 11 to 20 assessments\n   - Low: 10 or fewer assessments\n\n   Based on 10 assessments, the confidence level is: Low\n",
        },
    },
    "Image_Analysis": {},
}
