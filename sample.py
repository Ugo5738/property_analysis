import asyncio
import logging

import openai

from utils.openai_analysis import get_openai_chat_response

# Set your API key
openai.api_key = "sk-proj-aD2jNeQF3D6qNFNVoTGyT3BlbkFJaMaJQHZx2ccrImTWB3iL"

instruction = "Please improve and summarize the following property description and key features, and produce a reviewed description suitable for property buyers."
message = """
Description: A Lifestyle of Comfort and Elegance: Nestled in a desirable setting, Green Bank is a distinguished detached family home that has been thoughtfully upgraded to offer a sophisticated yet relaxed living experience. With an impressive layout spanning three floors, the home effortlessly blends modern convenience with timeless charm, making it the perfect retreat for contemporary family life.Versatile Living Spaces: Step inside and be welcomed by an expansive entrance hall that sets the tone for the spacious accommodation. The ground floor features distinct sitting and family rooms, with the sitting room opening directly to the side garden. The heart of the home is the substantial, open-plan kitchen and dining area, a vibrant space ideal for family gatherings and everyday living, with direct access to the beautifully maintained rear garden.Tailored to Family Needs: Offering six bedrooms across three floors, Green Bank caters to a wide range of family and generational needs. The first floor houses four bedrooms, including three generously sized doubles, and two well-appointed bathrooms, one of which is an en suite. The top floor provides an additional two double bedrooms, with one currently serving as a spacious study, perfect for working from home or easily converted into a luxurious dressing room.Exceptional Outdoor Living: The property's extensive outdoor space is equally impressive. The gardens, which wrap around three sides of the home, are designed with relaxation and entertainment in mind. With seating areas positioned to capture the day's sunlight, the rear garden, backing onto tranquil woodland, offers a private escape. Whether it's alfresco dining, family gatherings, or quiet moments surrounded by nature, the outdoor space caters to every occasion.Practicality Meets Style: Green Bank also offers extensive parking, including a carriage driveway, attached garage, and carport. Every detail, from the upgraded interiors to the well-planned outdoor spaces, enhances the home's convenience and aesthetic appeal, providing a seamless blend of luxury and practicality for modern family living.Council Tax Band G - £3,952.66paBrochuresWeb Details
Features: Elegant and Spacious Detached Family Home
Three Floors of Versatile Living
Open-Plan Kitchen and Dining
Six Bedrooms for Family Flexibility
Expansive, Private Outdoor Spaces
Desirable Location and Setting
Thoughtfully Upgraded Interiors
Multiple Sunlit Seating Areas Outdoors
Ample Parking and Carriage Driveway
Quiet Garden Backing onto Woodland
"""

prompt_format = {
    "type": "object",
    "properties": {
        "reviewed_description": {"type": "string"},
    },
    "required": ["reviewed_description"],
    "additionalProperties": False,
}
print(f"Prompt format: {prompt_format}")

try:
    reviewed_data = asyncio.run(
        get_openai_chat_response(instruction, message, prompt_format)
    )
    print(f"Received reviewed data: {reviewed_data}")
except Exception as e:
    print(f"Error occurred: {e}")


{
    "property_url": "https://www.onthemarket.com/details/14538477/",
    "stages": {
        "initial_categorization": [
            {"category": "external", "details": {"exterior_type": "others"}},
            {"category": "internal", "details": {"room_type": "dining room"}},
            {"category": "internal", "details": {"room_type": "kids' bedroom"}},
            {"category": "external", "details": {"exterior_type": "neighborhood"}},
            {"category": "internal", "details": {"room_type": "living room"}},
            {"category": "external", "details": {"exterior_type": "other"}},
            {"category": "internal", "details": {"room_type": "kitchen"}},
            {"category": "internal", "details": {"room_type": "bathroom"}},
            {"category": "internal", "details": {"room_type": "bedroom"}},
            {"category": "internal", "details": {"room_type": "bedroom"}},
            {"category": "external", "details": {"exterior_type": "front yard"}},
            {"category": "others", "details": {"others": "public transportation"}},
            {"category": "external", "details": {"exterior_type": "backyard"}},
            {"category": "external", "details": {"exterior_type": "backyard"}},
            {"category": "internal", "details": {"room_type": "guest bathroom"}},
            {"category": "external", "details": {"exterior_type": "neighborhood"}},
        ],
        "grouped_images": {
            "external": {
                "front_garden_space": [1, 4, 6, 11, 16],
                "back_garden_space": [13, 14],
            },
            "internal": {
                "living_space": [2, 5],
                "bedroom_space": [3, 9, 10],
                "kitchen_space": [7],
                "bathroom_space": [8, 15],
            },
            "others": {"others": [12]},
        },
        "merged_images": {
            "external_front_garden_space": [
                "/code/property_analysis/media/merged_property_images/merged_image_1_b0T4myI.jpg",
                "/code/property_analysis/media/merged_property_images/merged_image_2_LWcrfgI.jpg",
            ],
            "internal_living_space": [
                "/code/property_analysis/media/merged_property_images/merged_image_3_gt0EjHG.jpg"
            ],
            "internal_bedroom_space": [
                "/code/property_analysis/media/merged_property_images/merged_image_4_wnPu3yk.jpg"
            ],
            "internal_kitchen_space": [
                "/code/property_analysis/media/merged_property_images/merged_image_5_CHL14fL.jpg"
            ],
            "internal_bathroom_space": [
                "/code/property_analysis/media/merged_property_images/merged_image_6_AhkPEwr.jpg"
            ],
            "others_others": [
                "/code/property_analysis/media/merged_property_images/merged_image_7_wzdBZnp.jpg"
            ],
            "external_back_garden_space": [
                "/code/property_analysis/media/merged_property_images/merged_image_8_k8fwVKO.jpg"
            ],
        },
        "detailed_analysis": {
            "external_front_garden_space": [
                {
                    "image_number": 1,
                    "condition_label": "excellent",
                    "reasoning": "The house and surroundings are impeccably maintained and presented. The landscaping is professional, with a variety of well-maintained plants and a neat lawn. The hardscaping and driveway are high-quality and in excellent condition, contributing to the overall high standard of appearance.",
                }
            ],
            "internal_living_space": [
                {
                    "image_number": 1,
                    "condition_label": "excellent",
                    "reasoning": "The space features modern finishes, stylish furniture, and cohesive design. It is exceptionally well-presented and maintained, aligning with the Excellent category criteria.",
                },
                {
                    "image_number": 2,
                    "condition_label": "excellent",
                    "reasoning": "This room also displays high-end, contemporary furniture and fixtures. The attention to detail in design and decor, combined with impeccable staging, matches the standards for Excellent.",
                },
            ],
            "internal_bedroom_space": [
                {
                    "image_number": 1,
                    "condition_label": "above average",
                    "reasoning": "This room features well-maintained decor and furniture with a cohesive theme. It has an appealing color scheme and is generally tidy. However, it does not reach the 'Excellent' standard due to slight clutter and less high-end finishes.",
                },
                {
                    "image_number": 2,
                    "condition_label": "excellent",
                    "reasoning": "This room is well-designed with high-end finishes, modern fixtures, and stylish decor. It has a cohesive and elegant aesthetic, similar to the reference 'Excellent' images, making it highly appealing and well-maintained.",
                },
                {
                    "image_number": 3,
                    "condition_label": "excellent",
                    "reasoning": "The room showcases high-quality furniture and fixtures, with impeccable staging and a contemporary design. The finishes are modern and the presentation is on par with a show home, aligning with the 'Excellent' category.",
                },
                {
                    "image_number": 4,
                    "condition_label": "not present",
                    "reasoning": "The 2x2 grid only contains three images, without a fourth image to assess.",
                },
            ],
            "internal_kitchen_space": [
                {
                    "image_number": 1,
                    "condition_label": "excellent",
                    "reasoning": "The kitchen and dining area is modern and very well maintained. It features high-end finishes and fixtures, contemporary furniture, a cohesive design, and desirable features like a large sliding door letting in natural light. The staging and presentation are impeccable, making it comparable to a show home.",
                }
            ],
            "internal_bathroom_space": [
                {
                    "image_number": 1,
                    "condition_label": "excellent",
                    "reasoning": "The bathroom features high-end, modern finishes and fixtures, stylish and contemporary furniture and décor, and impeccable presentation and staging. The cohesive design and well-maintained appearance align with the criteria for an excellent condition.",
                },
                {
                    "image_number": 2,
                    "condition_label": "excellent",
                    "reasoning": "The second bathroom has good quality finishes, looks modern and clean, has a well-proportioned layout, and features a cohesive color scheme. The skylight provides ample natural light, enhancing the overall appeal. The design complements the house architecture well, and overall cleanliness matches the excellent condition criteria.",
                },
            ],
            "external_back_garden_space": [
                {
                    "image_number": 1,
                    "condition_label": "excellent",
                    "reasoning": "The front garden features professional landscaping with a well-maintained lawn, cohesive design that complements the house, and an inviting entrance. There is no visible clutter, and the overall presentation is impeccable.",
                },
                {
                    "image_number": 2,
                    "condition_label": "excellent",
                    "reasoning": "The back garden showcases a professionally maintained lawn with defined spaces for different activities, cohesive landscaping that complements the architecture, clear pathways, and no visible weeds or overgrowth. The setting is highly appealing and well-presented.",
                },
            ],
        },
        "overall_condition": {
            "overall_condition_label": "Excellent",
            "average_score": 4.6,
            "distribution": {
                "poor": 0.06666666666666667,
                "above average": 0.13333333333333333,
                "excellent": 0.8,
            },
            "condition_distribution": {
                "poor": 6.666666666666667,
                "above average": 13.333333333333334,
                "excellent": 80.0,
            },
            "areas_of_concern": 1,
            "confidence": "Medium",
            "explanation": "\nDetailed calculation of overall property condition:\n\n1. Total number of valid assessments: 15\n\n2. Condition counts:\n   - Poor: 1\n   - Above average: 2\n   - Excellent: 12\n\n3. Calculation of average score:\n   - Each condition is assigned a value: Excellent (5), Above Average (4), Average (3), Below Average (2), Poor (1)\n   - Total value: 69 (sum of all condition values)\n   - Average score: 69 / 15 = 4.60\n\n4. Distribution of conditions:\n   - Poor: 6.67%\n   - Above average: 13.33%\n   - Excellent: 80.00%\n\n5. Areas of concern (conditions below average): 1\n\n6. Overall rating determination:\n   - Excellent: 4.5 and above\n   - Good: 3.5 to 4.49\n   - Average: 2.5 to 3.49\n   - Below Average: 1.5 to 2.49\n   - Poor: Below 1.5\n\n   Based on the average score of 4.60, the overall rating is: Excellent\n\n7. Confidence level:\n   - High: More than 20 assessments\n   - Medium: 11 to 20 assessments\n   - Low: 10 or fewer assessments\n\n   Based on 15 assessments, the confidence level is: Medium\n",
        },
    },
    "Image_Analysis": {},
}


{
    "property_url": "https://www.onthemarket.com/details/14538477/",
    "stages": {
        "download": {
            "successful_downloads": [
                289,
                290,
                291,
                292,
                293,
                294,
                295,
                296,
                297,
                298,
                299,
                300,
                301,
                302,
                303,
                304,
            ],
            "failed_downloads": [],
        },
        "initial_categorization": [
            {"category": "unknown", "details": {"type": "unknown"}},
            {"category": "internal", "details": {"room_type": "bedroom_space"}},
            {
                "category": "external",
                "details": {"exterior_type": "front_garden_space"},
            },
            {"category": "internal", "details": {"room_type": "kitchen_space"}},
            {"category": "internal", "details": {"room_type": "bathroom_space"}},
            {"category": "internal", "details": {"room_type": "kitchen_space"}},
            {"category": "internal", "details": {"room_type": "bedroom_space"}},
            {
                "category": "external",
                "details": {"exterior_type": "front_garden_space"},
            },
            {"category": "internal", "details": {"room_type": "bedroom_space"}},
            {"category": "external", "details": {"exterior_type": "back_garden_space"}},
            {
                "category": "external",
                "details": {"exterior_type": "front_garden_space"},
            },
            {"category": "internal", "details": {"room_type": "bathroom_space"}},
            {
                "category": "external",
                "details": {"exterior_type": "front_garden_space"},
            },
            {
                "category": "external",
                "details": {"exterior_type": "front_garden_space"},
            },
            {"category": "internal", "details": {"room_type": "living_space"}},
            {"category": "external", "details": {"exterior_type": "back_garden_space"}},
        ],
        "grouped_images": {
            "internal": {
                "bedroom_space": [290, 295, 297],
                "kitchen_space": [292, 294],
                "bathroom_space": [293, 300],
                "living_space": [303],
            },
            "external": {
                "front_garden_space": [291, 296, 299, 301, 302],
                "back_garden_space": [298, 304],
            },
        },
        "merged_images": {},
        "detailed_analysis": {},
        "overall_condition": {},
    },
    "Image_Analysis": {},
}


# https://botpress.com/

# https://docs.nlkit.com/nlux

# https://www.voiceflow.com/

# https://botonic.io/


# framework that is js, react, next, based that has the functionality of botpress or voice flow and the seamless integration into the javascript webapp like nlux
# chatbot first javascript frontend
