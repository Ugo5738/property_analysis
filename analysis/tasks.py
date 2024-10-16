import ssl

import aiohttp
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from analysis.models import (
    AnalysisTask,
    GroupedImages,
    MergedPropertyImage,
    Property,
    PropertyImage,
)
from utils.image_processing import download_images
from utils.property_analysis import process_property


@shared_task
def analyze_property(property_id, task_id, user_id, job_id):
    async_to_sync(analyze_property_async)(property_id, task_id, user_id, job_id)


async def analyze_property_async(property_id, task_id, user_id, job_id):
    channel_layer = get_channel_layer()
    property_instance = await Property.objects.aget(id=property_id)
    task_instance = await AnalysisTask.objects.aget(id=task_id)

    async def update_progress(stage, message, progress):
        task_instance.status = stage
        task_instance.progress = progress
        task_instance.stage = stage
        task_instance.stage_progress[stage] = progress
        await task_instance.asave()
        await channel_layer.group_send(
            f"analysis_{user_id}",
            {
                "type": "analysis_progress",
                "message": {"stage": stage, "message": message, "progress": progress},
            },
        )

    try:
        # Download images
        await update_progress("download", "Downloading images", 0)

        # Create an SSL context that does not verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Retrieve scraped data from scraper app
        async with aiohttp.ClientSession() as session:
            async with session.get(
                # f"http://analysis-scraper-app:8001/api/site-scrapers/scrape/{job_id}/data/",
                f"https://52.23.156.175/api/site-scrapers/scrape/{job_id}/data/",
                timeout=10,
                ssl=ssl_context,
            ) as response:
                if response.status != 200:
                    raise Exception(
                        f"Failed to retrieve scraped data. Status code: {response.status}"
                    )
                scraped_data = await response.json()
                scraped_data = scraped_data.get("data")

        if not scraped_data:
            update_progress("error", "No data received from scraper app.", 0)
            return

        # Save scraped data to your main app's database
        property_instance.address = scraped_data.get("address")
        property_instance.price = scraped_data.get("price")
        property_instance.bedrooms = scraped_data.get("bedrooms")
        property_instance.bathrooms = scraped_data.get("bathrooms")
        property_instance.size = scraped_data.get("size")
        property_instance.house_type = scraped_data.get("house_type")
        property_instance.agent = scraped_data.get("agent")
        property_instance.description = scraped_data.get("description")
        property_instance.image_urls = scraped_data.get("images")
        property_instance.floorplan_urls = scraped_data.get("floorplans")
        await property_instance.asave()

        image_ids, failed_downloads = await download_images(
            property_instance, update_progress
        )
        property_instance.failed_downloads = failed_downloads

        # Process property
        result = await process_property(
            property_instance.url, image_ids, update_progress
        )

        # Update property with results
        property_instance.overall_condition = result["Condition"]
        property_instance.detailed_analysis = result["Detailed Analysis"]
        property_instance.overall_analysis = result["Overall Analysis"]
        await property_instance.asave()

        task_instance.status = "COMPLETED"
        task_instance.progress = 100.0
        await task_instance.asave()

        await update_progress("complete", "Analysis completed successfully", 100.0)
    except Exception as e:
        await update_progress("error", f"Error during analysis: {str(e)}", 0.0)
        task_instance.status = "ERROR"
        await task_instance.asave()
        property_instance.overall_condition = {"error": str(e)}
        await property_instance.asave()


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
