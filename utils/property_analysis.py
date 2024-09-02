import asyncio
import base64
import json

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile

from analysis.models import (
    GroupedImages,
    MergedPropertyImage,
    MergedSampleImage,
    Property,
    PropertyImage,
)
from utils.image_processing import merge_images
from utils.openai_analysis import (
    analyze_single_image,
    encode_image,
    update_prompt_json_file,
)
from utils.prompts import categorize_prompt, labelling_prompt, spaces


async def process_property(property_url, image_ids, update_progress):
    total_steps = 5  # Total number of main steps in the process
    step = 0  # Current step

    results = {
        "property_url": property_url,
        "stages": {
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

    # Step 1: Initial categorization
    step = 1
    await update_step_progress('categorization', 'Categorizing images', 0)
    await categorize_images(property_instance, image_ids, results, update_step_progress)

    # Step 2: Grouping images
    step = 2
    await update_step_progress('grouping', 'Grouping images by category', 0)
    await group_images(property_instance, results, update_step_progress)

    # Step 3: Merging images
    step = 3
    await update_step_progress('merging', 'Merging grouped images', 0)
    await merge_grouped_images(property_instance, results, update_step_progress)

    # Step 4: Detailed analysis
    step = 4
    await update_step_progress('analysis', 'Analyzing merged images', 0)
    all_condition_ratings = await analyze_merged_images(property_instance, results, update_step_progress)

    # Step 5: Overall condition calculation
    step = 5
    await update_step_progress('overall_analysis', 'Calculating overall property condition', 0)
    property_condition = analyze_property_condition(all_condition_ratings)
    results['stages']['overall_condition'] = property_condition
    print(f"This is the final results: {results}")
    await update_step_progress('overall_analysis', 'Finished calculating overall condition', 1)

    # Final result compilation
    final_result = {
        'Property URL': property_url,
        'Condition': property_condition,
        'Detailed Analysis': results['stages']['detailed_analysis'],
        'Analysis Stages': results['stages']
    }

    return final_result


async def categorize_images(property_instance, image_ids, results, update_step_progress):
    total_batches = (len(image_ids) + 3) // 4  # Round up division
    for i in range(0, len(image_ids), 4):
        batch = image_ids[i:i+4]
        if not batch:
            continue

        images = await sync_to_async(list)(PropertyImage.objects.filter(id__in=batch))
        merged_image = await merge_images(images)
        base64_encoded = base64.b64encode(merged_image).decode('utf-8')
        # base64_encoded = f"data:image/png;base64,{base64_encoded}"
        base64_image = f"data:image/jpeg;base64,{base64_encoded}"

        structured_output = await analyze_single_image(categorize_prompt, base64_image)
        category_result = structured_output["response_content"]

        if category_result:
            result = json.loads(category_result)
            print(f"This is the result: {result}")

            await update_prompt_json_file(spaces, result)
            print("Finished updating json file")

            for index, image_id in enumerate(batch):
                if index < len(result.get('images', [])):
                    img_result = result['images'][index]
                    await update_property_image_category(image_id, img_result)
                    results['stages']['initial_categorization'].append(img_result)
                else:
                    print(f"No result for image at index {index}")

        await update_step_progress('categorization', f'Categorized batch {i+1}/{total_batches}', (i+1)/total_batches)


async def update_property_image_category(image_id, category_info):
    property_image = await PropertyImage.objects.aget(id=image_id)
    property_image.main_category = category_info.get('category', '')
    details = category_info.get('details', {})

    # Load the data.json content
    with open('utils/data.json', 'r') as f:
        data_json = json.load(f)

    # Determine sub_category and space_type
    if property_image.main_category == 'internal':
        sub_category = details.get('room_type', '')
        space_type = sub_category
    elif property_image.main_category == 'external':
        sub_category = details.get('exterior_type', '')
        space_type = sub_category
    else:
        sub_category = details.get('others', '')
        space_type = sub_category

    # Find the matching subcategory in data.json
    mapped_sub_category = 'others'
    for key, values in data_json.items():
        if sub_category.lower() in [v.lower() for v in values]:
            mapped_sub_category = key
            break

    property_image.sub_category = mapped_sub_category
    property_image.room_type = space_type  # change room_type to space_type in the database
    await property_image.asave()


async def group_images(property_instance, results, update_step_progress):
    images = await sync_to_async(list)(PropertyImage.objects.filter(property=property_instance))

    for image in images:
        group, created = await GroupedImages.objects.aget_or_create(
            property=property_instance,
            main_category=image.main_category,
            sub_category=image.sub_category
        )
        await group.images.aadd(image)

        if created:
            results['stages']['grouped_images'].setdefault(image.main_category, {})[image.sub_category] = []
        results['stages']['grouped_images'][image.main_category][image.sub_category].append(image.id)

    await update_step_progress('grouping', 'Finished grouping images', 1)


async def merge_grouped_images(property_instance, results, update_step_progress):
    grouped_images = await sync_to_async(list)(GroupedImages.objects.filter(property=property_instance))
    total_groups = len(grouped_images)

    for idx, group in enumerate(grouped_images):
        images = await sync_to_async(list)(group.images.all())

        # Split into subgroups of 4 if there are more than 4 images
        subgroups = [images[i:i+4] for i in range(0, len(images), 4)]

        for subgroup in subgroups:
            merged_image = await merge_images(subgroup)

            merged_property_image = await MergedPropertyImage.objects.acreate(
                property=property_instance,
                main_category=group.main_category,
                sub_category=group.sub_category
            )
            filename = f"merged_image_{merged_property_image.id}.jpg"
            await sync_to_async(merged_property_image.image.save)(filename, ContentFile(merged_image), save=True)

            # results['stages']['merged_images'][f"{group.main_category}_{group.sub_category}"] = merged_property_image.image.path
            # Store the path in results
            results['stages']['merged_images'].setdefault(f"{group.main_category}_{group.sub_category}", []).append(
                # merged_property_image.image.path
                merged_property_image.image.url
            )
        await update_step_progress('merging', f'Merged group {idx+1}/{total_groups}', (idx+1)/total_groups)


async def analyze_merged_images(property_instance, results, update_step_progress):
    merged_images = await sync_to_async(list)(MergedPropertyImage.objects.filter(property=property_instance))
    total_analyses = len(merged_images)
    all_condition_ratings = []

    for idx, merged_image in enumerate(merged_images):
        sample_images = await sync_to_async(list)(
            MergedSampleImage.objects.filter(
                category=merged_image.main_category,
                subcategory=merged_image.sub_category
            )
        )

        # Encode sample images
        sample_images_dict = {}
        for item in sample_images:
            encoded_image = encode_image(item.image)
            sample_images_dict[item.condition] = f"data:image/jpeg;base64,{encoded_image}"

        if not sample_images_dict:
            continue

        conditions = list(sample_images_dict.keys())
        full_prompt = (f"{labelling_prompt}\n\nSample images are provided for the following conditions: {', '.join(conditions)}. "
                       f"The target images (2x2 grid) follow these sample images.")

        # Encode the merged image
        encoded_merged_image = encode_image(merged_image.image)
        base64_merged_image = f"data:image/jpeg;base64,{encoded_merged_image}"

        try:
            structured_output = await analyze_single_image(full_prompt, base64_merged_image, sample_images_dict)
            if "error" in structured_output:
                print(f"Error in analyze_single_image: {structured_output['error']}")
                continue
            result = structured_output["response_content"]
        except Exception as e:
            print(f"Exception in analyze_single_image: {str(e)}")
            continue

        if result:
            try:
                parsed_result = json.loads(result)
                image_analyses = parsed_result.get('images', [])

                processed_analyses = []
                for analysis in image_analyses:
                    condition_label = analysis.get("condition", "Unknown").lower()
                    all_condition_ratings.append(condition_label)
                    processed_analyses.append({
                        "image_number": analysis.get("image_tag_number", "Unknown"),
                        "condition_label": condition_label,
                        "reasoning": analysis.get("reasoning", "No reasoning provided")
                    })

                results['stages']['detailed_analysis'][f"{merged_image.main_category}_{merged_image.sub_category}"] = processed_analyses

                # Update individual PropertyImage instances
                group_images = await sync_to_async(list)(
                    PropertyImage.objects.filter(
                        property=property_instance,
                        main_category=merged_image.main_category,
                        sub_category=merged_image.sub_category
                    )
                )
                for img, analysis in zip(group_images, processed_analyses):
                    img.condition_label = analysis['condition_label']
                    img.reasoning = analysis['reasoning']
                    await img.asave()

            except json.JSONDecodeError:
                print(f"Error decoding JSON for {merged_image.main_category}_{merged_image.sub_category}: {result}")

        await update_step_progress('analysis', f'Analyzed group {idx+1}/{total_analyses}', (idx+1)/total_analyses)
    return all_condition_ratings


def analyze_property_condition(conditions):
    condition_values = {"excellent": 5, "above average": 4, "average": 3, "below average": 2, "poor": 1}
    valid_conditions = [c.lower() for c in conditions if c.lower() in condition_values]

    if not valid_conditions:
        return "Insufficient data"

    total_value = sum(condition_values[c] for c in valid_conditions)
    average_value = total_value / len(valid_conditions)

    condition_counts = {c: valid_conditions.count(c) for c in set(valid_conditions)}
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
