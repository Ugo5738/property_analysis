import json
import os
from collections import defaultdict

from asgiref.sync import sync_to_async
from django.db import transaction

from analysis.models import (
    MergedPropertyImage,
    MergedSampleImage,
    Property,
    PropertyImage,
    SampleImage,
)
from utils.image_processing import (
    group_images_by_category,
    merge_group_images,
    merge_images,
)
from utils.openai_analysis import analyze_single_image, update_prompt_json_file
from utils.prompts import categorize_prompt, labelling_prompt, spaces


async def create_and_cache_sample_images():
    categories = {
        "internal": ["living_spaces", "kitchen_spaces", "bathroom_spaces", "bedroom_spaces"],
        "external": ["front_garden_spaces", "back_garden_spaces"],
        "floor plan": ["ground_floor", "first_floor", "site_plan"]
    }
    conditions = ["excellent", "above_average", "below_average", "poor"]

    for main_category, subcategories in categories.items():
        for subcategory in subcategories:
            for condition in conditions:
                sample_images = await sync_to_async(SampleImage.objects.filter)(
                    category=main_category,
                    subcategory=subcategory,
                    condition=condition
                )
                image_paths = [image.image.path for image in sample_images]

                if image_paths:
                    merged_image = await merge_group_images(image_paths, f"{main_category}_{subcategory}_{condition}", condition)
                    if merged_image:
                        await sync_to_async(MergedSampleImage.objects.update_or_create)(
                            category=main_category,
                            subcategory=subcategory,
                            condition=condition,
                            defaults={'image': merged_image}
                        )
                else:
                    print(f"No sample images found for {main_category}/{subcategory}/{condition}")

    return await sync_to_async(MergedSampleImage.objects.all)()


# Wrap synchronous functions with sync_to_async
merge_group_images = sync_to_async(merge_group_images)

# Cache sample images asynchronously
CACHED_SAMPLE_IMAGES = None

async def get_cached_sample_images():
    global CACHED_SAMPLE_IMAGES
    if CACHED_SAMPLE_IMAGES is None:
        CACHED_SAMPLE_IMAGES = await create_and_cache_sample_images()
    return CACHED_SAMPLE_IMAGES


async def analyze_category(main_category, subcategory, merged_path):
    """
    Analyze a merged image for a specific category using the appropriate sample images and prompt.
    """

    sample_images = await sync_to_async(MergedSampleImage.objects.filter)(
        category=main_category,
        subcategory=subcategory
    ).values_list('condition', 'image', named=True)
    sample_images_dict = {item.condition: item.image.path for item in sample_images}

    if not sample_images_dict:
        raise ValueError(f"No sample images available for {main_category}_{subcategory}")

    # Select the appropriate prompt
    if main_category == "internal" or main_category == "external":
        prompt = labelling_prompt
    else:
        raise ValueError(f"Unknown main category: {main_category}")

    # Construct the full prompt
    conditions = list(sample_images_dict.keys())
    full_prompt = (f"{prompt}\n\nSample images are provided for the following conditions: {', '.join(conditions)}. "
                   f"The target images (2x2 grid) follow these sample images.")

    # Analyze using the updated analyze_single_image function
    structured_output = await analyze_single_image(full_prompt, merged_path, sample_images_dict)
    result = structured_output["response_content"]
    if result:
        try:
            parsed_result = json.loads(result)
            if not isinstance(parsed_result, dict) or 'images' not in parsed_result:
                print(f"Unexpected result format for {main_category}_{subcategory}: {parsed_result}")
                return None

            image_analyses = parsed_result['images']
            if not image_analyses:
                print(f"No image analyses found for {main_category}_{subcategory}")
                return None

            # Process all images in the 2x2 grid
            processed_analyses = []
            for analysis in image_analyses:
                processed_analyses.append({
                    "image_number": analysis.get("image_tag_number", "Unknown"),
                    "condition_label": analysis.get("condition", "Unknown").lower(),  # Convert to lowercase
                    "reasoning": analysis.get("reasoning", "No reasoning provided")
                })
            return processed_analyses
        except json.JSONDecodeError:
            print(f"Error decoding JSON for {main_category}_{subcategory}: {result}")
            return None
        except Exception as e:
            print(f"Unexpected error analyzing {main_category}_{subcategory}: {str(e)}")
            print(f"Result: {result}")
            return None
    return None


def normalize_category(category_info):
    category = category_info.get("category", "").lower()
    details = category_info.get("details", {})

    if category == "internal":
        room_type = details.get("room_type", "unknown").lower()
        for area, room_types in spaces.items():
            if room_type in room_types:
                return {"category": "internal", "details": {"room_type": area}}
        return {"category": "internal", "details": {"room_type": "unknown"}}
    elif category == "external":
        exterior_type = details.get("exterior_type", "unknown").lower()
        for area, exterior_types in spaces.items():
            if exterior_type in exterior_types:
                return {"category": "external", "details": {"exterior_type": area}}
        return {"category": "external", "details": {"exterior_type": "unknown"}}
    elif category == "floor plan":
        floor_type = details.get("floor_type", "unknown").lower()
        return {"category": "floor plan", "details": {"floor_type": floor_type}}
    else:
        return {"category": "unknown", "details": {"type": "unknown"}}


@sync_to_async
def get_property_images(image_ids):
    return list(PropertyImage.objects.filter(id__in=image_ids))


async def process_images(image_ids, is_batch):
    images = await get_property_images(image_ids)
    if is_batch:
        merged_image = await merge_images(images)
        image_to_analyze = merged_image
    else:
        image_to_analyze = images[0].image

    structured_output = await analyze_single_image(categorize_prompt, image_to_analyze)
    category_result = structured_output["response_content"]

    if category_result:
        result = json.loads(category_result)

        await update_prompt_json_file(spaces, result)
        print("Finished updating json file")

        try:
            if "images" in result:
                return {"images": [normalize_category(img) for img in result["images"]]}
            else:
                return {"images": [normalize_category(result)]}
        except json.JSONDecodeError:
            return None
    return None


def analyze_property_condition(conditions):
    condition_values = {"excellent": 5, "above average": 4, "average": 3, "below average": 2, "poor": 1}
    valid_conditions = [c.lower() for c in conditions if c.lower() in condition_values]

    if not valid_conditions:
        return "Insufficient data"

    condition_counts = defaultdict(int)
    for c in valid_conditions:
        condition_counts[c] += 1

    total_value = sum(condition_values[c] for c in valid_conditions)
    average_value = total_value / len(valid_conditions)

    distribution = {c: count / len(valid_conditions) for c, count in condition_counts.items()}

    below_average_count = sum(1 for c in valid_conditions if condition_values[c] < 3)

    if average_value >= 4.5:
        rating = "Excellent"
    elif 3.5 <= average_value < 4.5:
        rating = "Good"
    elif 2.5 <= average_value < 3.5:
        rating = "Average"
    elif 1.5 <= average_value < 2.5:
        rating = "Below Average"
    else:
        rating = "Poor"

    condition_percentages = {c: (count / len(valid_conditions)) * 100 for c, count in condition_counts.items()}

    result = {
        "overall_condition_label": rating,
        "average_score": round(average_value, 2),
        "distribution": distribution,
        "condition_distribution": condition_percentages,
        "areas_of_concern": below_average_count,
        "confidence": "High" if len(valid_conditions) > 20 else "Medium" if len(valid_conditions) > 10 else "Low"
    }

    explanation = f"""
Detailed calculation of overall property condition:

1. Total number of valid assessments: {len(valid_conditions)}

2. Condition counts:
{chr(10).join(f"   - {cond.capitalize()}: {count}" for cond, count in condition_counts.items())}

3. Calculation of average score:
   - Each condition is assigned a value: Excellent (5), Above Average (4), Average (3), Below Average (2), Poor (1)
   - Total value: {total_value} (sum of all condition values)
   - Average score: {total_value} / {len(valid_conditions)} = {average_value:.2f}

4. Distribution of conditions:
{chr(10).join(f"   - {cond.capitalize()}: {dist:.2%}" for cond, dist in distribution.items())}

5. Areas of concern (conditions below average): {below_average_count}

6. Overall rating determination:
   - Excellent: 4.5 and above
   - Good: 3.5 to 4.49
   - Average: 2.5 to 3.49
   - Below Average: 1.5 to 2.49
   - Poor: Below 1.5

   Based on the average score of {average_value:.2f}, the overall rating is: {rating}

7. Confidence level:
   - High: More than 20 assessments
   - Medium: 11 to 20 assessments
   - Low: 10 or fewer assessments

   Based on {len(valid_conditions)} assessments, the confidence level is: {result['confidence']}
"""

    result["explanation"] = explanation
    return result


async def update_property_image_categories(property_instance, all_categories):
    @sync_to_async
    def update_single_image(idx, image_id, category_details):
        with transaction.atomic():
            file_name_prefix = f"property_images/property_{property_instance.id}_image_{idx}"

            try:
                # Try to retrieve the PropertyImage instance matching exactly the file name
                property_image_instance = PropertyImage.objects.get(image=file_name_prefix + '.jpg')
            except PropertyImage.DoesNotExist:
                # If the exact match is not found, look for a file name with a random string appended
                property_image_instance = PropertyImage.objects.get(image__startswith=f"{file_name_prefix}_")

            property_image_instance.category = {
                'category': category_details['category'],
                'details': category_details['details']
            }

            property_image_instance.save()
            print(f"Updated category for idx {idx} and image {image_id}")

    for idx, (image_id, category_details) in enumerate(all_categories):
        await update_single_image(idx, image_id, category_details)


async def process_property(property_url, image_ids, update_progress):
    total_steps = 6  # Total number of main steps in the process
    step = 0  # Current step

    results = {
        "property_url": property_url,
        "stages": {
            "download": {"successful_downloads": image_ids, "failed_downloads": []},
            "initial_categorization": [],
            "grouped_images": {},
            "merged_images": {},
            "detailed_analysis": {},
            "overall_condition": {}
        },
        "Image_Analysis": {}
    }

    property_instance = await sync_to_async(Property.objects.get)(url=property_url)

    async def update_step_progress(stage, message, sub_progress=0):
        nonlocal step
        progress = (step / total_steps + sub_progress / total_steps) * 100
        await update_progress(stage, message, progress)

    all_categories = []

    # Step 1: Initial categorization
    step = 1
    await update_progress('categorization', 'Categorizing images', 0)
    total_batches = (len(image_ids) + 3) // 4  # Round up division
    for i in range(0, len(image_ids), 4):
        batch = image_ids[i:i+4]
        if not batch:
            continue
        category_result = await process_images(batch, is_batch=(len(batch) > 1))
        if category_result:
            results['stages']['initial_categorization'].extend(category_result['images'])
            all_categories.extend(zip(batch, category_result['images']))

        await update_step_progress('categorization', f'Categorized batch {i+1}/{total_batches}', (i+1)/total_batches)

    # update property images model with the categorization of each image
    await update_property_image_categories(property_instance, all_categories)

    # Step 2: Grouping images
    step = 2
    await update_step_progress('grouping', 'Grouping images by category', 0)
    grouped_images = await group_images_by_category([img for img, _ in all_categories], [cat for _, cat in all_categories])
    results['stages']['grouped_images'] = grouped_images
    await update_step_progress('grouping', 'Finished grouping images', 1)
    print(f"This is the result so far 1: {results}")
    merged_group_images = {}
    analysis_results = {}
    all_condition_ratings = []

    # Step 3: Merging images
    step = 3
    await update_step_progress('merging', 'Merging grouped images', 0)
    total_groups = sum(len(subcategories) for subcategories in grouped_images.values())
    group_count = 0

    for main_category, subcategories in grouped_images.items():
        for subcategory, image_ids in subcategories.items():
            if not image_ids:
                continue

            group_name = f"{main_category}_{subcategory}"
            images = await get_property_images(image_ids)
            print("These are the images I am checking: ", images)
            merged_image = await merge_images(images)
            if merged_image:
                merged_group_image = await sync_to_async(MergedPropertyImage.objects.create)(
                    property=property_instance,
                    image=merged_image,
                    category=group_name
                )
                merged_group_images[group_name] = merged_group_image.image.path
                results['stages']['merged_images'][group_name] = merged_image

            group_count += 1
            await update_step_progress('merging', f'Merged group {group_count}/{total_groups}', group_count/total_groups)
        print(f"This is the result so far 2: {results}")

    # Step 4: Detailed analysis
    step = 4
    await update_step_progress('analysis', 'Analyzing merged images', 0)
    total_analyses = len(merged_group_images)
    analysis_count = 0

    for group_name, merged_image in merged_group_images.items():
        main_category, subcategory = group_name.split('_')
        try:
            category_analysis = await analyze_category(main_category, subcategory, merged_image)
            if category_analysis:
                analysis_results[group_name] = category_analysis
                all_condition_ratings.extend([analysis['condition_label'] for analysis in category_analysis])
                results['stages']['detailed_analysis'][group_name] = category_analysis
        except Exception as e:
            results['stages']['detailed_analysis'][group_name] = {'error': str(e)}

        analysis_count += 1
        await update_step_progress('analysis', f'Analyzed group {analysis_count}/{total_analyses}', analysis_count/total_analyses)

    # Step 5: Overall condition calculation
    step = 5
    await update_step_progress('overall_analysis', 'Calculating overall property condition', 0)
    property_condition = analyze_property_condition(all_condition_ratings)
    results['stages']['overall_condition'] = property_condition
    await update_step_progress('overall_analysis', 'Finished calculating overall condition', 1)

    # Step 6: Final result compilation
    step = 6
    await update_step_progress('compilation', 'Compiling final results', 0)
    final_result = {
        'Property URL': property_url,
        'Condition': property_condition,
        'Detailed Analysis': analysis_results,
        'Failed Downloads': results['stages']['download']['failed_downloads'],
        'Analysis Stages': results['stages']
    }
    await update_step_progress('compilation', 'Finished compiling results', 1)

    return final_result


# remove normalization
# include the room name in the image models
# limit the reasoning tokens
# what is the maximum number of reasoning tokens, multiply that number by 3 and use that as the limit for the reasoning tokens
