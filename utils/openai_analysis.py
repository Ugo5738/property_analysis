import base64
import json
import os

from property_analysis.config.base_config import openai_client as client


def encode_image(image_file):
    with image_file.open("rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


async def analyze_single_image(text_prompt, target_image, sample_images_dict=None):
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": text_prompt,
                    },
                ],
            }
        ]

        if sample_images_dict:
            for condition, image_base64 in sample_images_dict.items():
                messages[0]["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_base64,
                            "detail": "low",
                        },
                    }
                )

        if not target_image.startswith("data:image/jpeg;base64,"):
            raise ValueError("Target image must be a base64-encoded JPEG string")

        if isinstance(target_image, str):
            if target_image.startswith("data:image/jpeg;base64,"):
                messages[0]["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": target_image,
                            "detail": "low",
                        },
                    }
                )
            elif os.path.isfile(target_image):
                base64_image = encode_image(target_image)
                messages[0]["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "low",
                        },
                    }
                )
            elif target_image.startswith("http"):
                messages[0]["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {"url": target_image, "detail": "high"},
                    },
                )
            else:
                print(f"Error: Unrecognized image format for {target_image}")
                return None
        else:
            print(f"Error: target_image is not a string: {type(target_image)}")
            return None

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
        )

        structured_output = {
            "response_content": response.choices[0].message.content,
            "prompt_tokens": response.usage.prompt_tokens,
            "prompt_tokens_cost": (response.usage.prompt_tokens * 5) / 1000000,
            "completion_tokens": response.usage.completion_tokens,
            "completion_tokens_cost": (response.usage.completion_tokens * 15) / 1000000,
        }

        return structured_output

    except Exception as e:
        print(f"Error in analyze_single_image: {str(e)}")
        return {"error": str(e)}


# update the JSON file
async def update_prompt_json_file(spaces, classifications):
    for classification in classifications["images"]:
        category = classification["category"]
        details = classification["details"]

        if category == "internal":
            room_type = details.get("room_type")
            if room_type and room_type not in sum(spaces.values(), []):
                spaces["living_space"].append(room_type)
            if "others" in details:
                other_type = details["others"]
                if other_type not in spaces["others"]:
                    spaces["others"].append(other_type)

        elif category == "external":
            exterior_type = details.get("exterior_type")
            if exterior_type and exterior_type not in sum(spaces.values(), []):
                spaces["front_garden_space"].append(exterior_type)
            if "others" in details:
                other_type = details["others"]
                if other_type not in spaces["others"]:
                    spaces["others"].append(other_type)

        elif category == "floor plan":
            floor_type = details.get("floor_type")
            if floor_type and floor_type not in spaces["others"]:
                spaces["others"].append(floor_type)

        elif category == "others":
            other_type = details["others"]
            if other_type not in spaces["others"]:
                spaces["others"].append(other_type)

    # Remove duplicates by converting lists to sets and back to lists
    for key in spaces:
        spaces[key] = list(set(spaces[key]))
    # Write the updated JSON back to the file
    with open("utils/data.json", "w") as file:
        json.dump(spaces, file, indent=4)
