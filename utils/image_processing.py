import asyncio
import base64
import io
import os
import re
from urllib.parse import urlparse

import aiohttp
import clip
import cv2
import numpy as np
import pandas as pd
import requests
import torch
from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from analysis.models import PropertyImage
from property_analysis.config.logging_config import configure_logger

logger = configure_logger(__name__)


# Initialize CLIP model and preprocessing
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)


async def compute_image_embedding(image_content):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_compute_embedding, image_content)


def sync_compute_embedding(image_content):
    image = Image.open(io.BytesIO(image_content)).convert("RGB")
    image_input = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        embedding = model.encode_image(image_input)
    embedding = embedding.cpu().numpy().flatten()
    return embedding


def compute_embedding(image_path):
    image = Image.open(image_path).convert("RGB")
    image_input = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        embedding = model.encode_image(image_input)
    embedding = embedding.cpu().numpy().flatten()
    return embedding


# Define headers to mimic a real browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def get_primary_domain(url):
    parsed_url = urlparse(url)
    domain_parts = parsed_url.netloc.split(".")
    if len(domain_parts) > 2:
        primary_domain = ".".join(domain_parts[-2:])
    else:
        primary_domain = parsed_url.netloc
    return primary_domain


def scrape_images(url):
    image_urls = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Wait for network to be idle and for the page to load
        try:
            page.goto(url, timeout=120000)  # Increased timeout to 60 seconds
            logger.info(f"Waiting for images on {url}")
            page.wait_for_selector(
                "li.slide img", timeout=60000
            )  # Increased timeout to 60 seconds
            logger.info(f"Images found on {url}")
        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout error for {url}: {e}")
            browser.close()
            return []
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            browser.close()
            return []

        # Scrape the image URLs
        try:
            image_elements = page.query_selector_all("li.slide img")
            for img in image_elements:
                src_img = img.get_attribute("src")
                primary_domain = get_primary_domain(src_img)
                if src_img and primary_domain in src_img and "logo" not in src_img:
                    image_urls.add(src_img)
        except Exception as e:
            logger.error(f"Error scraping images from {url}: {e}")

        browser.close()
    return list(image_urls)


def extract_images(property_url):
    property_id = re.search(r"/details/(\d+)", property_url).group(1)
    photo_url = f"https://www.onthemarket.com/details/{property_id}/#/photos/1"
    return scrape_images(photo_url)


def select_larger_image(images):
    def get_image_dimensions(url):
        match = re.search(r"(\d+)x(\d+)", url)
        if match:
            return int(match.group(1)) * int(match.group(2))
        return 0

    image_dict = {}
    for url in images:
        match = re.search(r"/properties/(\d+)/(\d+)/image-(\d+)-", url)
        if match:
            prop_id, image_id = match.group(1), match.group(3)
            key = f"{prop_id}_{image_id}"
            dimensions = get_image_dimensions(url)
            if key not in image_dict or dimensions > image_dict[key][1]:
                image_dict[key] = (url, dimensions)
        else:
            image_dict[url] = (url, get_image_dimensions(url))

    return [img[0] for img in image_dict.values()]


def get_image_urls(property_url):
    images = extract_images(property_url)
    selected_images = select_larger_image(images)
    return selected_images


async def download_images(
    property_instance, update_progress, max_retries=3, retry_delay=1, use_selenium=False
):
    image_ids = []
    failed_downloads = []
    driver = None

    if use_selenium:
        # Note: Selenium operations are synchronous, so we'll need to use run_in_executor for these parts
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)

    try:
        for idx, image_url in enumerate(property_instance.image_urls):
            for attempt in range(max_retries):
                try:
                    if use_selenium:
                        img_content = await sync_to_async(download_with_selenium)(
                            driver, image_url
                        )
                    else:
                        img_content = await download_with_requests(image_url)

                    if img_content:
                        # print(f"Image content downloaded, length: {len(img_content)}")

                        # Generate a filename
                        file_name = f"property_{property_instance.id}_image_{idx}.jpg"

                        property_image = await PropertyImage.objects.acreate(
                            property=property_instance,
                            original_url=image_url,
                            created_at=timezone.now(),
                        )

                        # Save the image content
                        await sync_to_async(property_image.image.save)(
                            file_name, ContentFile(img_content), save=False
                        )

                        # Compute and store embedding and save the PropertyImage instance
                        embedding = await compute_image_embedding(img_content)
                        property_image.embedding = embedding.tolist()
                        await property_image.asave()

                        logger.info(
                            f"PropertyImage object created with ID: {property_image.id}"
                        )

                        # # Verify file was saved
                        # if property_image.image:
                        #     # logger.info(f"Image file saved at: {property_image.image.path}")
                        #     logger.info(f"File exists: {await sync_to_async(os.path.exists)(property_image.image.path)}")
                        # else:
                        #     logger.info("Image file was not saved properly")

                        image_ids.append(property_image.id)
                        await update_progress(
                            "download",
                            f"Downloaded image {idx + 1}",
                            (idx + 1) / len(property_instance.image_urls) * 100,
                        )
                        break  # Successful download, move to next image
                except Exception as e:
                    logger.info(f"Error downloading image {idx}: {str(e)}")
                    if attempt == max_retries - 1:
                        failed_downloads.append((idx, image_url, str(e)))
                    else:
                        await asyncio.sleep(retry_delay * (attempt + 1))
        logger.info("Finished processing all images")
    finally:
        if driver:
            await sync_to_async(driver.quit)()

    return image_ids, failed_downloads


def download_with_selenium(driver, image_url):
    try:
        driver.get(image_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "img"))
        )
        # Find the largest image on the page
        images = driver.find_elements(By.TAG_NAME, "img")
        largest_image = max(
            images,
            key=lambda img: int(img.get_attribute("width") or 0)
            * int(img.get_attribute("height") or 0),
        )

        # Get the source of the largest image
        img_src = largest_image.get_attribute("src")

        # Download the image using requests
        response = requests.get(img_src, timeout=30)
        response.raise_for_status()

        img = Image.open(io.BytesIO(response.content))
        img_io = io.BytesIO()
        img.save(img_io, format="JPEG")
        return ContentFile(img_io.getvalue())
    except (TimeoutException, WebDriverException) as e:
        print(f"Selenium error: {str(e)}")
        return None


async def download_with_requests(image_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, timeout=30) as response:
            if response.status == 200:
                return await response.read()
    return None


def resize_with_aspect_ratio(image, target_size):
    img = Image.open(image)
    img = img.convert("RGB")
    img_array = np.array(img)
    h, w = img_array.shape[:2]
    scale = min(target_size[0] / h, target_size[1] / w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized_image = cv2.resize(img_array, (new_w, new_h))

    top = (target_size[0] - new_h) // 2
    bottom = target_size[0] - new_h - top
    left = (target_size[1] - new_w) // 2
    right = target_size[1] - new_w - left

    color = [0, 0, 0]  # black
    padded_image = cv2.copyMakeBorder(
        resized_image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color
    )
    return Image.fromarray(padded_image)


async def merge_images(image_objects, condition=None):
    target_size = (256, 256)
    resized_images = [
        resize_with_aspect_ratio(img.image, target_size) for img in image_objects
    ]
    num_images = len(resized_images)

    if num_images == 1:
        merged_image = np.array(resized_images[0])
    elif num_images == 2:
        merged_image = np.zeros((256, 512, 3), dtype=np.uint8)
        merged_image[:, :256] = np.array(resized_images[0])
        merged_image[:, 256:] = np.array(resized_images[1])
        cv2.line(merged_image, (256, 0), (256, 256), (0, 0, 255), 2)
    else:
        merged_image = np.zeros((512, 512, 3), dtype=np.uint8)
        positions = [(0, 0), (0, 256), (256, 0), (256, 256)]
        for i, image in enumerate(resized_images[:4]):
            y, x = positions[i]
            merged_image[y : y + 256, x : x + 256] = np.array(image)[
                :, :, :3
            ]  # Ensure we only take RGB channels
        cv2.line(merged_image, (256, 0), (256, 512), (0, 0, 255), 2)
        cv2.line(merged_image, (0, 256), (512, 256), (0, 0, 255), 2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    font_color = (255, 255, 255)
    thickness = 2

    label_positions = [(10, 30), (266, 30), (10, 286), (266, 286)]

    for i in range(min(num_images, 4)):
        cv2.putText(
            merged_image,
            str(i + 1),
            label_positions[i],
            font,
            font_scale,
            font_color,
            thickness,
            cv2.LINE_AA,
        )

    if condition:
        condition = condition.upper()
        text_size = cv2.getTextSize(condition, font, font_scale, thickness)[0]
        text_x = (merged_image.shape[1] - text_size[0]) // 2
        text_y = merged_image.shape[0] // 2
        cv2.putText(
            merged_image,
            condition,
            (text_x, text_y),
            font,
            font_scale,
            (0, 255, 0),
            thickness,
            cv2.LINE_AA,
        )

    # Convert the merged image to base64
    img_byte_arr = io.BytesIO()
    Image.fromarray(merged_image).save(img_byte_arr, format="JPEG")
    return img_byte_arr.getvalue()


def get_base64_image(image):
    base64_encoded = base64.b64encode(image).decode("utf-8")
    # return f"data:image/png;base64,{base64_encoded}"
    return f"data:image/jpeg;base64,{base64_encoded}"


async def group_images_by_category(image_ids, categories):
    grouped_images = {
        "internal": {},
        "external": {},
        "floor plan": {},
    }
    for image_id, category_info in zip(image_ids, categories):
        category = category_info.get("category", "").lower()
        details = category_info.get("details", {})

        if category == "internal":
            room_type = details.get("room_type", "unknown").lower()
            if room_type != "unknown":
                grouped_images["internal"].setdefault(room_type, []).append(image_id)
        elif category == "external":
            exterior_type = details.get("exterior_type", "unknown").lower()
            if exterior_type != "unknown":
                grouped_images["external"].setdefault(exterior_type, []).append(
                    image_id
                )
        elif category == "floor plan":
            floor_type = details.get("floor_type", "unknown").lower()
            if floor_type != "unknown":
                grouped_images["floor plan"].setdefault(floor_type, []).append(image_id)

    # Remove empty categories
    return {k: v for k, v in grouped_images.items() if v}


{
    "property_url": "https://www.rightmove.co.uk/properties/146759381",
    "stages": {
        "initial_categorization": [
            {"category": "internal", "details": {"room_type": "kitchen"}},
            {"category": "internal", "details": {"room_type": "bedroom"}},
            {"category": "internal", "details": {"room_type": "living room"}},
            {"category": "external", "details": {"exterior_type": "balcony"}},
            {"category": "internal", "details": {"room_type": "bathroom"}},
            {"category": "internal", "details": {"room_type": "guest bedroom"}},
            {"category": "external", "details": {"exterior_type": "other"}},
            {"category": "internal", "details": {"room_type": "shower room"}},
            {"category": "internal", "details": {"room_type": "living room"}},
            {"category": "external", "details": {"exterior_type": "other"}},
        ],
        "grouped_images": {
            "internal": {
                "kitchen_space": [11],
                "bedroom_space": [12, 16],
                "living_space": [13, 19],
                "bathroom_space": [15, 18],
            },
            "external": {"front_garden_space": [14, 17, 20]},
        },
        "merged_images": {
            "internal_kitchen_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_6_4VKJVme.jpg"
            ],
            "internal_bedroom_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_7_0rzDkoR.jpg"
            ],
            "internal_living_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_8_eusKrht.jpg"
            ],
            "external_front_garden_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_9_tBM90gZ.jpg"
            ],
            "internal_bathroom_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_10_oTHSAie.jpg"
            ],
        },
        "detailed_analysis": {
            "internal_kitchen_space": [
                {
                    "image_number": 1,
                    "condition_label": "Excellent",
                    "condition_score": 85,
                    "reasoning": "The kitchen in this image has a modern design with high-end, sleek finishes and fixtures. The space is well-lit, featuring stylish cabinetry and a cohesive color palette. The flooring appears pristine, with no visible signs of wear or damage, aligning with the excellent condition criteria.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_0_yMYh5A6.jpg",
                    "image_id": 11,
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
                    "condition_score": 90,
                    "reasoning": "The room is highly stylish with a contemporary design, cohesive color scheme, and modern furnishings. It is well-maintained with no visible signs of wear or damage, fitting the 'Excellent' category.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_1_BC3NVVP.jpg",
                    "image_id": 12,
                    "similarities": {
                        "above_average": 0.8705994753723505,
                        "below_average": 0.8367324696245676,
                        "excellent": 0.8549990130109195,
                        "poor": 0.7822495579066492,
                    },
                },
                {
                    "image_number": 2,
                    "condition_label": "Excellent",
                    "condition_score": 85,
                    "reasoning": "The room is in pristine condition with high-quality finishes and fixtures. It has a minimalist yet cohesive design with no visible wear or maintenance issues, aligning with the 'Excellent' category.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_5_MoSKcfv.jpg",
                    "image_id": 16,
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
                    "condition_score": 90,
                    "reasoning": "The space features modern finishes, stylish furniture, and a cohesive design. It presents a high level of upkeep with immaculate condition and high-quality materials, consistent with an 'Excellent' standard.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_2_Lkety0p.jpg",
                    "image_id": 13,
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
                    "condition_score": 88,
                    "reasoning": "This room also showcases high-end finishes, contemporary decor, and a cohesive color scheme. The space is well-maintained with no visible wear, aligning well with the 'Excellent' criteria.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_8_3sh64Rg.jpg",
                    "image_id": 19,
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
                    "condition_score": 85,
                    "reasoning": "Impeccable maintenance with a well-maintained balcony, beautiful views, and stylish furniture that contributes to a high-end appearance.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_3_Zn8kRiL.jpg",
                    "image_id": 14,
                    "similarities": {
                        "above_average": 0.691769454432527,
                        "below_average": 0.6588049612303928,
                        "excellent": 0.6811463126466217,
                        "poor": 0.6335610979692958,
                    },
                },
                {
                    "image_number": 2,
                    "condition_label": "Excellent",
                    "condition_score": 85,
                    "reasoning": "Modern building with high-quality materials and design. The structure is in excellent condition, with no visible signs of wear.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_6_HYVEkxA.jpg",
                    "image_id": 17,
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
                    "condition_score": 75,
                    "reasoning": "Well-maintained outdoor space with tidy landscaping and modern building appearance, but less pristine than the previous images.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_9_sh04Eky.jpg",
                    "image_id": 20,
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
                    "condition_score": 90,
                    "reasoning": "The bathroom is very well-maintained with high-end, modern finishes and fixtures. The design is cohesive, featuring a sleek, contemporary appearance. The structural elements are pristine, and the space is immaculately presented, aligning closely with the 'Excellent' examples.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_4_tyBWf7J.jpg",
                    "image_id": 15,
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
                    "condition_score": 85,
                    "reasoning": "The shower area is impeccably maintained with modern fixtures and a clean aesthetic. The space is well-designed, featuring high-quality materials and excellent presentation. It aligns closely with the 'Excellent' criteria, though with slightly less decorative flair compared to image 1.",
                    "image_url": "https://propertyanalysisstorage.s3.amazonaws.com/media/property_images/property_1_image_7_Oa1sVBd.jpg",
                    "image_id": 18,
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
            "average_score": 85.8,
            "label_distribution": {"Excellent": 0.9, "Above Average": 0.1},
            "areas_of_concern": 0,
            "confidence": "Low",
            "explanation": "\nDetailed calculation of overall property condition:\n\n1. Total number of valid assessments: 10\n\n2. Average score: 85.80\n\n3. Distribution of condition labels:\n   - Excellent: 90.00%\n   - Above Average: 10.00%\n\n4. Areas of concern (scores below 40%): 0\n\n5. Overall rating determination:\n   - Excellent: 80% and above\n   - Above Average: 60% to 79%\n   - Average: 40% to 59%\n   - Below Average: 20% to 39%\n   - Poor: Below 20%\n\n   Based on the average score of 85.80, the overall rating is: Excellent\n\n6. Confidence level:\n   - High: More than 20 assessments\n   - Medium: 11 to 20 assessments\n   - Low: 10 or fewer assessments\n\n   Based on 10 assessments, the confidence level is: Low\n",
        },
    },
    "Image_Analysis": {},
}


{
    "property_url": "https://www.rightmove.co.uk/properties/154166495",
    "stages": {
        "initial_categorization": [
            {"category": "internal", "details": {"room_type": "hallway"}},
            {"category": "internal", "details": {"room_type": "bathroom"}},
            {"category": "internal", "details": {"room_type": "bedroom"}},
            {"category": "internal", "details": {"room_type": "kitchen"}},
            {"category": "internal", "details": {"room_type": "dining room"}},
            {"category": "internal", "details": {"room_type": "hallway"}},
            {"category": "internal", "details": {"room_type": "bedroom"}},
        ],
        "grouped_images": {
            "internal": {
                "living_space": [1, 5, 6],
                "bathroom_space": [2],
                "bedroom_space": [3, 7],
                "kitchen_space": [4],
            }
        },
        "merged_images": {
            "internal_living_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_1_lqLWiex.jpg"
            ],
            "internal_bathroom_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_2_zb9ZqdT.jpg"
            ],
            "internal_bedroom_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_3_hFNDkAz.jpg"
            ],
            "internal_kitchen_space": [
                "https://propertyanalysisstorage.s3.amazonaws.com/media/merged_property_images/merged_image_4_jhDhw8T.jpg"
            ],
        },
        "detailed_analysis": {},
        "overall_condition": "Insufficient data",
    },
    "Image_Analysis": {},
}
