import asyncio
import base64
import io
import os
import re
from urllib.parse import urlparse

import aiohttp
import cv2
import numpy as np
import pandas as pd
import requests
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
            page.wait_for_selector("li.slide img", timeout=60000)  # Increased timeout to 60 seconds
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


async def download_images(property_instance, update_progress, max_retries=3, retry_delay=1, use_selenium=False):
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
                        img_content = await sync_to_async(download_with_selenium)(driver, image_url)
                    else:
                        img_content = await download_with_requests(image_url)

                    if img_content:
                        # print(f"Image content downloaded, length: {len(img_content)}")

                        # Generate a filename
                        file_name = f"property_{property_instance.id}_image_{idx}.jpg"

                        property_image = await PropertyImage.objects.acreate(
                            property=property_instance,
                            created_at=timezone.now()
                        )

                        # Save the image content
                        await sync_to_async(property_image.image.save)(file_name, ContentFile(img_content), save=False)

                        # Now save the PropertyImage instance
                        await property_image.asave()

                        print(f"PropertyImage object created with ID: {property_image.id}")

                        # Verify file was saved
                        if property_image.image:
                            # print(f"Image file saved at: {property_image.image.path}")
                            print(f"File exists: {await sync_to_async(os.path.exists)(property_image.image.path)}")
                        else:
                            print("Image file was not saved properly")

                        image_ids.append(property_image.id)
                        await update_progress('download', f'Downloaded image {idx + 1}', (idx + 1) / len(property_instance.image_urls) * 100)
                        break  # Successful download, move to next image
                except Exception as e:
                    print(f"Error downloading image {idx}: {str(e)}")
                    if attempt == max_retries - 1:
                        failed_downloads.append((idx, image_url, str(e)))
                    else:
                        await asyncio.sleep(retry_delay * (attempt + 1))
        print("Finished processing all images")
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
        largest_image = max(images, key=lambda img: int(img.get_attribute("width") or 0) * int(img.get_attribute("height") or 0))

        # Get the source of the largest image
        img_src = largest_image.get_attribute("src")

        # Download the image using requests
        response = requests.get(img_src, timeout=30)
        response.raise_for_status()

        img = Image.open(io.BytesIO(response.content))
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
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
    img = img.convert('RGB')
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
    padded_image = cv2.copyMakeBorder(resized_image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return Image.fromarray(padded_image)


async def merge_images(image_objects, condition=None):
    target_size = (256, 256)
    resized_images = [resize_with_aspect_ratio(img.image, target_size) for img in image_objects]
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
            merged_image[y:y+256, x:x+256] = np.array(image)[:, :, :3]  # Ensure we only take RGB channels
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
    Image.fromarray(merged_image).save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()


def get_base64_image(image):
    base64_encoded = base64.b64encode(image).decode('utf-8')
    # return f"data:image/png;base64,{base64_encoded}"
    return f"data:image/jpeg;base64,{base64_encoded}"


async def group_images_by_category(image_ids, categories):
    grouped_images = {
        "internal": {},
        "external": {},
        "floor plan": {},
    }
    for image_id, category_info in zip(image_ids, categories):
        category = category_info.get('category', '').lower()
        details = category_info.get('details', {})

        if category == 'internal':
            room_type = details.get('room_type', 'unknown').lower()
            if room_type != 'unknown':
                grouped_images['internal'].setdefault(room_type, []).append(image_id)
        elif category == 'external':
            exterior_type = details.get('exterior_type', 'unknown').lower()
            if exterior_type != 'unknown':
                grouped_images['external'].setdefault(exterior_type, []).append(image_id)
        elif category == 'floor plan':
            floor_type = details.get('floor_type', 'unknown').lower()
            if floor_type != 'unknown':
                grouped_images['floor plan'].setdefault(floor_type, []).append(image_id)

    # Remove empty categories
    return {k: v for k, v in grouped_images.items() if v}
