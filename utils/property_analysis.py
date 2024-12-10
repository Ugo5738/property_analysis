import base64
import json
from collections import Counter

import numpy as np
from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from sklearn.metrics.pairwise import cosine_similarity

from analysis.models import (
    GroupedImages,
    MergedPropertyImage,
    MergedSampleImage,
    Property,
    PropertyImage,
    SampleImage,
)
from property_analysis.config.logging_config import configure_logger
from utils.image_processing import compute_embedding, merge_images
from utils.openai_analysis import (
    analyze_single_image,
    encode_image,
    update_prompt_json_file,
)
from utils.prompts import categorize_prompt, get_prompts, spaces

logger = configure_logger(__name__)


async def process_property(property_url, image_ids, update_progress, phone_number):
    total_steps = 5  # Total number of main steps in the process
    step = 0  # Current step

    results = {
        "property_url": property_url,
        "stages": {
            "initial_categorization": [],
            "grouped_images": {},
            "merged_images": {},
            "detailed_analysis": {},
            "overall_condition": {},
        },
        "Image_Analysis": {},
    }

    try:
        property_instance = await sync_to_async(Property.objects.get)(
            url=property_url, phone_number=phone_number
        )
    except Property.DoesNotExist:
        error_message = "Property not found for the given URL and user."
        logger.error(error_message)
        await update_progress("error", error_message, 0.0)
        return {"error": error_message}
    except Property.MultipleObjectsReturned:
        error_message = "Multiple properties found for the given URL and user."
        logger.error(error_message)
        await update_progress("error", error_message, 0.0)
        return {"error": error_message}

    async def update_step_progress(stage, message, sub_progress=0):
        nonlocal step
        progress = (step / total_steps + sub_progress / total_steps) * 100
        await update_progress(stage, message, progress)

    try:
        # Step 1: Initial categorization
        step = 1
        await update_step_progress("categorization", "Categorizing images", 0)
        await categorize_images(
            property_instance, image_ids, results, update_step_progress
        )
        print("Done categorizing...")

        # Step 2: Grouping images
        step = 2
        await update_step_progress("grouping", "Grouping images by category", 0)
        await group_images(property_instance, results, update_step_progress)
        print("Done grouping...")

        # Step 3: Merging images
        step = 3
        await update_step_progress("merging", "Merging grouped images", 0)
        await merge_grouped_images(property_instance, results, update_step_progress)
        print("Done merging...")

        # Step 4: Detailed analysis
        step = 4
        await update_step_progress("analysis", "Analyzing merged images", 0)
        all_condition_labels, all_condition_scores = await analyze_merged_images(
            property_instance, results, update_step_progress
        )
        print("Done analyzing...")

        # Step 5: Overall condition calculation
        step = 5
        await update_step_progress(
            "overall_analysis", "Calculating overall property condition", 0
        )
        print("Done updating...")

        property_condition = analyze_property_condition(
            all_condition_labels, all_condition_scores, property_instance.bedrooms
        )
        results["stages"]["overall_condition"] = property_condition

        logger.info(f"==================== Final Result completed ====================")

        await update_step_progress(
            "overall_analysis", "Finished calculating overall condition", 1
        )

        # Final result compilation
        final_result = {
            "Property URL": property_url,
            "Condition": property_condition,
            "Detailed Analysis": results["stages"]["detailed_analysis"],
            "Overall Analysis": results,
            "Analysis Stages": results["stages"],
        }

        return final_result

    except Exception as e:
        error_message = f"Error during analysis: {str(e)}"
        logger.error(error_message)
        import traceback

        traceback.print_exc()
        await update_progress("error", error_message, 0.0)
        return {"error": error_message}


async def categorize_images(
    property_instance, image_ids, results, update_step_progress
):
    total_batches = (len(image_ids) + 3) // 4  # Round up division
    for batch_num, i in enumerate(range(0, len(image_ids), 4), 1):
        batch = image_ids[i : i + 4]
        if not batch:
            continue

        images = await sync_to_async(list)(PropertyImage.objects.filter(id__in=batch))
        merged_image = await merge_images(images)
        base64_encoded = base64.b64encode(merged_image).decode("utf-8")
        # base64_encoded = f"data:image/png;base64,{base64_encoded}"
        base64_image = f"data:image/jpeg;base64,{base64_encoded}"

        structured_output = analyze_single_image(categorize_prompt, base64_image)
        category_result = structured_output["response_content"]

        if category_result:
            result = json.loads(category_result)
            logger.info(f"This is the result: {result}")

            await update_prompt_json_file(spaces, result)
            logger.info("Finished updating json file")

            for index, image_id in enumerate(batch):
                if index < len(result.get("images", [])):
                    img_result = result["images"][index]
                    await update_property_image_category(image_id, img_result)
                    results["stages"]["initial_categorization"].append(img_result)
                else:
                    logger.info(f"No result for image at index {index}")

        await update_step_progress(
            "categorization",
            f"Categorized batch {batch_num}/{total_batches}",
            (batch_num) / total_batches,
        )


def standardize_condition_label(label: str) -> str:
    """
    Standardizes the condition label to match predefined labels.
    """
    label = label.strip().lower().replace("_", " ").replace("-", " ")
    mapping = {
        "excellent": "Excellent",
        "above average": "Above Average",
        "average": "Average",
        "below average": "Below Average",
        "poor": "Poor",
    }
    return mapping.get(label, "Average")


async def update_property_image_category(image_id, category_info):
    property_image = await PropertyImage.objects.aget(id=image_id)
    property_image.main_category = category_info.get("category", "")
    details = category_info.get("details", {})

    # Load the data.json content
    with open("utils/data.json", "r") as f:
        data_json = json.load(f)

    # Determine sub_category and space_type
    if property_image.main_category == "internal":
        sub_category = details.get("room_type", "")
        space_type = sub_category
    elif property_image.main_category == "external":
        sub_category = details.get("exterior_type", "")
        space_type = sub_category
    else:
        sub_category = details.get("others", "")
        space_type = sub_category

    # Find the matching subcategory in data.json
    mapped_sub_category = "others"
    for key, values in data_json.items():
        if sub_category.lower() in [v.lower() for v in values]:
            mapped_sub_category = key
            break

    property_image.sub_category = mapped_sub_category
    property_image.room_type = (
        space_type  # change room_type to space_type in the database
    )
    await property_image.asave()

    # Logging for debugging
    logger.info(
        f"Image ID {image_id} categorized as {property_image.main_category} - {property_image.sub_category}"
    )


async def group_images(property_instance, results, update_step_progress):
    try:
        logger.info(f"Starting grouping images for property: {property_instance.url}")
        images = await sync_to_async(list)(
            PropertyImage.objects.filter(property=property_instance)
        )
        logger.info(f"Total images found: {len(images)}")

        for image in images:
            try:
                logger.info(
                    f"Processing image: {image.id} - Main category: {image.main_category}, Sub category: {image.sub_category}"
                )
                group, created = await GroupedImages.objects.aget_or_create(
                    property=property_instance,
                    main_category=image.main_category,
                    sub_category=image.sub_category,
                )
                await group.images.aadd(image)

                if created:
                    logger.info(
                        f"Created new group: {image.main_category} - {image.sub_category}"
                    )
                    results["stages"]["grouped_images"].setdefault(
                        image.main_category, {}
                    )[image.sub_category] = []

                results["stages"]["grouped_images"][image.main_category][
                    image.sub_category
                ].append(image.id)
                logger.info(
                    f"Added image {image.id} to group {image.main_category} - {image.sub_category}"
                )

            except Exception as e:
                logger.error(f"Error processing image {image.id}: {str(e)}")
                import traceback

                traceback.print_exc()

        logger.info("Finished grouping all images")
        await update_step_progress("grouping", "Finished grouping images", 1)

    except Exception as e:
        logger.error(f"Error in group_images function: {str(e)}")
        import traceback

        traceback.print_exc()
        raise  # Re-raise the exception to be caught by the calling function

    logger.info("Group images results:")
    logger.info(json.dumps(results["stages"]["grouped_images"], indent=2))


async def merge_grouped_images(property_instance, results, update_step_progress):
    try:
        logger.info(
            f"Starting merging grouped images for property: {property_instance.url}"
        )
        grouped_images = await sync_to_async(list)(
            GroupedImages.objects.filter(property=property_instance)
        )
        total_groups = len(grouped_images)
        logger.info(f"Total grouped images: {total_groups}")

        for idx, group in enumerate(grouped_images):
            try:
                logger.info(
                    f"Processing group: {group.id} - {group.main_category} - {group.sub_category}"
                )
                images = await sync_to_async(list)(group.images.all())
                logger.info(f"Images in group: {len(images)}")

                # Split into subgroups of 4 if there are more than 4 images
                subgroups = [images[i : i + 4] for i in range(0, len(images), 4)]

                for subgroup_idx, subgroup in enumerate(subgroups):
                    try:
                        logger.info(
                            f"Merging subgroup {subgroup_idx + 1} of {len(subgroups)}"
                        )
                        merged_image = await merge_images(subgroup)

                        merged_property_image = (
                            await MergedPropertyImage.objects.acreate(
                                property=property_instance,
                                main_category=group.main_category,
                                sub_category=group.sub_category,
                            )
                        )
                        filename = f"merged_image_{merged_property_image.id}.jpg"
                        await sync_to_async(merged_property_image.image.save)(
                            filename, ContentFile(merged_image), save=True
                        )
                        # Associate images used to create the merged image
                        await merged_property_image.images.aset(subgroup)

                        results["stages"]["merged_images"].setdefault(
                            f"{group.main_category}_{group.sub_category}", []
                        ).append(merged_property_image.image.url)
                        logger.info(f"Created merged image: {merged_property_image.id}")

                    except Exception as e:
                        logger.error(
                            f"Error merging subgroup {subgroup_idx + 1}: {str(e)}"
                        )
                        import traceback

                        traceback.print_exc()

            except Exception as e:
                logger.error(f"Error processing group {group.id}: {str(e)}")
                import traceback

                traceback.print_exc()

            await update_step_progress(
                "merging",
                f"Merged group {idx+1}/{total_groups}",
                (idx + 1) / total_groups,
            )

        logger.info("Finished merging all grouped images")

    except Exception as e:
        logger.error(f"Error in merge_grouped_images function: {str(e)}")
        import traceback

        traceback.print_exc()
        raise  # Re-raise the exception to be caught by the calling function

    logger.info("Merged images results:")
    logger.info(json.dumps(results["stages"]["merged_images"], indent=2))


async def analyze_merged_images(property_instance, results, update_step_progress):
    # Fetch the prompt
    labelling_prompt = await sync_to_async(get_prompts)()

    merged_images = await sync_to_async(list)(
        MergedPropertyImage.objects.filter(property=property_instance)
    )
    total_analyses = len(merged_images)

    all_condition_scores = []
    all_condition_labels = []

    for idx, merged_image in enumerate(merged_images):
        # Retrieve sample images and their embeddings for the same category and subcategory
        sample_merged_images = await sync_to_async(list)(
            MergedSampleImage.objects.filter(
                category=merged_image.main_category,
                subcategory=merged_image.sub_category,
            )
        )

        # Encode sample images
        sample_images_dict = {}
        conditions = []
        # For each sample merged image (should be one per condition)
        for sample_merged_image in sample_merged_images:
            condition_label = sample_merged_image.condition
            encoded_image = encode_image(sample_merged_image.image)
            sample_images_dict[condition_label] = (
                f"data:image/jpeg;base64,{encoded_image}"
            )
            conditions.append(condition_label)

        if not sample_images_dict:
            continue

        # Encode the merged image
        encoded_merged_image = encode_image(merged_image.image)
        base64_merged_image = f"data:image/jpeg;base64,{encoded_merged_image}"

        full_prompt = (
            f"{labelling_prompt}\n\nSample images are provided for the following conditions: {', '.join(conditions)}. "
            f"The target images (2x2 grid) follow these sample images."
        )

        try:
            structured_output = analyze_single_image(
                full_prompt, base64_merged_image, sample_images_dict
            )
            if "error" in structured_output:
                logger.info(
                    f"Error in analyze_single_image: {structured_output['error']}"
                )
                continue
            result = structured_output["response_content"]
            # print("This is the result I want to check: ", result)
        except Exception as e:
            logger.error(f"Exception in analyze_single_image: {str(e)}")
            continue

        if result:
            try:
                parsed_result = json.loads(result)
                image_analyses = parsed_result.get("images", [])

                processed_analyses = []

                # Retrieve individual target images associated with the merged image
                images_in_merged_image = await sync_to_async(list)(
                    merged_image.images.all().order_by("id")
                )

                # Ensure embeddings are available for target images
                for img in images_in_merged_image:
                    if img.embedding is None:
                        # Compute and store embedding if not available
                        image_file = img.image.path
                        embedding = compute_embedding(image_file)
                        img.embedding = embedding.tolist()
                        await img.asave()
                    else:
                        embedding = np.array(img.embedding)

                    # Store the embedding in a variable for later use
                    img.embedding_array = embedding

                # Map image_tag_number to PropertyImage
                # Assuming images are ordered corresponding to quadrants 1-4
                image_quadrant_mapping = {
                    i + 1: img for i, img in enumerate(images_in_merged_image)
                }

                # -------------------------
                # Compute Similarity Scores
                # -------------------------
                for analysis in image_analyses:
                    image_number = int(analysis.get("image_tag_number"))
                    img = image_quadrant_mapping.get(image_number)
                    if not img:
                        logger.warning(
                            f"No image found for image_number {image_number}"
                        )
                        continue

                    condition_label_raw = analysis.get("condition", "Average")
                    condition_label = standardize_condition_label(condition_label_raw)
                    condition_score = int(analysis.get("condition_score", 50))
                    all_condition_scores.append(condition_score)
                    all_condition_labels.append(condition_label)

                    # Compute similarity scores for this target image
                    similarities_per_condition = {}

                    for sample_merged_image in sample_merged_images:
                        condition_label_sample = sample_merged_image.condition

                        # Retrieve individual sample images from the quadrant mapping
                        sample_quadrant_mapping = (
                            sample_merged_image.quadrant_mapping
                        )  # Dict mapping str quadrant number to SampleImage IDs
                        sample_images = []
                        for (
                            quadrant_num_str,
                            sample_img_id,
                        ) in sample_quadrant_mapping.items():
                            sample_img = await sync_to_async(SampleImage.objects.get)(
                                id=sample_img_id
                            )
                            if sample_img.embedding is not None:
                                sample_embedding = np.array(sample_img.embedding)
                            else:
                                # Compute and store embedding if not available
                                image_file = sample_img.image.path
                                sample_embedding = compute_embedding(image_file)
                                sample_img.embedding = sample_embedding.tolist()
                                await sample_img.asave()

                            # Compute similarity
                            similarity = cosine_similarity(
                                [img.embedding_array], [sample_embedding]
                            )
                            similarities_per_condition.setdefault(
                                condition_label_sample, []
                            ).append(similarity[0][0])

                    # Average similarity scores for each condition
                    avg_similarities = {
                        condition: sum(scores) / len(scores) if scores else 0
                        for condition, scores in similarities_per_condition.items()
                    }

                    processed_analysis = {
                        "image_number": image_number,
                        "condition_label": condition_label,
                        "condition_score": condition_score,
                        "reasoning": analysis.get("reasoning", "No reasoning provided"),
                        "image_url": img.image.url if img.image else None,
                        "image_id": img.id,
                        "similarities": avg_similarities,
                    }
                    processed_analyses.append(processed_analysis)

                    # Update individual PropertyImage instances
                    img.condition_label = condition_label
                    img.condition_score = condition_score
                    img.reasoning = analysis.get("reasoning", "No reasoning provided")
                    img.similarity_scores = avg_similarities
                    await img.asave()

                # Store the processed analyses in results
                key = f"{merged_image.main_category}_{merged_image.sub_category}"
                results["stages"]["detailed_analysis"].setdefault(key, []).extend(
                    processed_analyses
                )

            except json.JSONDecodeError:
                logger.error(
                    f"Error decoding JSON for {merged_image.main_category}_{merged_image.sub_category}: {result}"
                )

        await update_step_progress(
            "analysis",
            f"Analyzed group {idx+1}/{total_analyses}",
            (idx + 1) / total_analyses,
        )
    return all_condition_labels, all_condition_scores


def get_confidence_level(total_assessments, bedrooms):
    thresholds = {
        0: {"High": 4, "Medium": 2},  # Studio
        1: {"High": 6, "Medium": 4},
        2: {"High": 8, "Medium": 6},
        3: {"High": 10, "Medium": 8},
        4: {"High": 12, "Medium": 10},
        5: {"High": 15, "Medium": 12},  # 5+
    }

    if bedrooms is None:
        # Default thresholds
        if total_assessments > 20:
            return "High"
        elif total_assessments > 10:
            return "Medium"
        else:
            return "Low"
    else:
        if bedrooms >= 5:
            bedroom_key = 5
        else:
            bedroom_key = bedrooms

        bedroom_thresholds = thresholds.get(bedroom_key)
        if total_assessments >= bedroom_thresholds["High"]:
            return "High"
        elif total_assessments >= bedroom_thresholds["Medium"]:
            return "Medium"
        else:
            return "Low"


def analyze_property_condition(condition_labels, condition_scores, bedrooms):
    if not condition_scores:
        return "Insufficient data"

    average_score = sum(condition_scores) / len(condition_scores)

    # Determine overall condition label based on average score
    if average_score >= 75.01:
        rating = "Excellent"
    elif 50.01 <= average_score < 75:
        rating = "Above Average"
    elif 25.01 <= average_score < 50:
        rating = "Below Average"
    else:
        rating = "Poor"

    # Calculate distribution of condition labels
    label_counts = Counter(condition_labels)
    total_labels = len(condition_labels)
    if total_labels == 0:
        label_distribution = {}
    else:
        label_distribution = {
            label: count / total_labels for label, count in label_counts.items()
        }

    areas_of_concern = sum(1 for score in condition_scores if score < 40)
    total_assessments = len(condition_scores)

    # Get confidence level based on number of bedrooms
    confidence = get_confidence_level(total_assessments, bedrooms)

    # Fetch thresholds for explanation
    thresholds = {
        0: {
            "High": 4,
            "Medium": 2,
        },  # Studio ==> Review this because it could be a 1 bed
        1: {"High": 6, "Medium": 4},
        2: {"High": 8, "Medium": 6},
        3: {"High": 10, "Medium": 8},
        4: {"High": 12, "Medium": 10},
        5: {"High": 15, "Medium": 12},  # 5+
    }
    if bedrooms is None or bedrooms not in thresholds:
        bedroom_thresholds = {"High": "N/A", "Medium": "N/A"}
    else:
        bedroom_thresholds = thresholds.get(bedrooms if bedrooms < 5 else 5)

    # Generate detailed explanation
    explanation = f"""
Detailed calculation of overall property condition:

1. Total number of valid assessments: {len(condition_scores)}

2. Average score: {average_score:.2f}

3. Distribution of condition labels:
{chr(10).join(f"   - {label}: {dist:.2%}" for label, dist in label_distribution.items())}

4. Areas of concern (scores below 40%): {areas_of_concern}

5. Overall rating determination:
   - Excellent: 75.01% and above
   - Above Average: 50.01% to 75%
   - Below Average: 25.01% to 50%
   - Poor: Below 25%

   Based on the average score of {average_score:.2f}, the overall rating is: {rating}

6. Confidence level based on number of bedrooms ({bedrooms if bedrooms is not None else 'Unknown'} bedrooms):
   - High: {bedroom_thresholds['High']} or more assessments
   - Medium: {bedroom_thresholds['Medium']} to {int(bedroom_thresholds['High']) - 1 if bedroom_thresholds['High'] != 'N/A' else 'N/A'} assessments
   - Low: Fewer than {bedroom_thresholds['Medium']} assessments

   Based on {len(condition_scores)} assessments, the confidence level is: {confidence}
"""

    result = {
        "overall_condition_label": rating,
        "average_score": round(average_score, 2),
        "label_distribution": label_distribution,
        "total_assessments": total_assessments,
        "areas_of_concern": areas_of_concern,
        "confidence": confidence,
        "explanation": explanation,
    }
    return result


# 447841869521

# might need to work on studio, models.py, and analysis

# if the bedroom is 1 and there is a mention of studio in the description then the property type would be flat, apartment, or studio
