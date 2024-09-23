import json

# generally if an property has lifestyle images, it most likely is above average or excellent
# make the categorization output more flexible and then map the term. For terms outside the scope of categorization words, use the model to map the OOS to categorizations. i.e, let AI handle edge cases and update the code

# Read the JSON file
with open("utils/data.json", "r") as file:
    spaces = json.load(file)

internal_types = ", ".join(
    sum(
        (
            spaces[area]
            for area in [
                "living_space",
                "kitchen_space",
                "bathroom_space",
                "bedroom_space",
            ]
        ),
        [],
    )
)
external_types = ", ".join(
    sum((spaces[area] for area in ["front_garden_space", "back_garden_space"]), [])
)

categorize_prompt = f"""
You are an image classification assistant. Categorize each image as either "internal," "external," or "floor plan." Provide details based on the category:

- For "internal": Specify the room type from the following list:
  {internal_types}

- For "external": Specify the exterior type from the following list:
  {external_types}

- For "floor plan": Specify the plan type e.g. ground floor, first floor, site plan

- If the room or space type does exactly fit any of the labels given above, specify the space type label correctly into "internal", "external", "floor plan" or "others"

Always return the result in the following JSON format for each image:

{{
  "category": "internal" or "external" or "floor plan" or "others",
  "details": {{
    "room_type": "if category is "internal" specific room type"
    "exterior_type": "if category is "external" specific exterior type"
    "floor_type": "if category is "floor plan" specific floor plan type"
    "others": "if category is "others" specific space type"
  }}
}}

If processing multiple images, wrap the results in a "images" array:

{{
  "images": [
    {{
      "category": "...",
      "details": {{ ... }}
    }},
    {{
      "category": "...",
      "details": {{ ... }}
    }},
    ...
  ]
}}

Ensure consistency in naming and use lowercase for all types.
"""


internal_prompt = """
You are a seasoned realtor with 15 years of experience in the UK. Provide a detailed analysis of the internal image(s), considering Modernization, Fixtures and Fittings, Repair Needs.
Return the response in JSON format with the corresponding keys.

Sample format:
{
  "modernization": "your very concise description here",
  "fixtures_and_fittings": "your very concise description here",
  "repair_needs": "your very concise description here",
}
"""


external_prompt = """
You are a seasoned realtor with 15 years of experience in the UK. Provide a detailed analysis of the external image(s), considering Front & Back Garden, Curb Appeal.
Return the response in JSON format with the corresponding keys.

Sample format:
{
  "front_back_garden": "your very concise description here",
  "curb_appeal: "your very concise description here",
}
"""


floor_plan_prompt = """
You are a highly experienced architect with 20 years of experience specializing in evaluating floor plans in the UK. Provide a detailed analysis of the floor plan images provided. Consider:

1. Space Utilization: Is the space well-utilized or are there any areas that seem wasted?

Return the response in JSON format with the corresponding keys.

Sample format:
{
  "space_utilization": "your very concise description here",
}
"""


text_prompt = """
You are a highly experienced realtor with 10/15 years of experience specializing in valuing properties both internally and externally in the UK. Provide a detailed analysis of the images provided. Here are some aspects to consider, but feel free to add more:

1. Modernization: Is the property modernized or recently refurbished?
2. Fixtures and Fittings: Do the fixtures and fittings appear to be high-spec or low quality?
3. Refurbishment and Repair Needs: Is the property in need of any repairs?
4. Front & Back Garden: What is the state of the back garden?
5. Curb Appeal: Does the property have curb appeal or not?

If there are more than one property in the image usual characterized by multiples door, entrances, drive way etc, address each property separately.

Return the response in JSON format with the corresponding keys.
"""


observation_prompt = """
Analyze the given property image and categorize it based on your observations.
Pay attention to details such as paint quality, fixtures, signs of wear and tear, overall maintenance, and any other relevant features.
Determine whether the property is in good, average, below average, or poor condition.
Provide a detailed description of your observations and explain why you categorized the image that way.
"""


first_prompt = """
Here's a breakdown for each category:

Excellent:
- Uses superlative language like "beautifully presented", "stunning", "luxury", or "immaculate"
- Mentions high-end features or amenities (e.g., hot tubs, ensuite bathrooms, bespoke fittings)
- Emphasizes spaciousness and generous proportions
- Highlights recent renovations or modern upgrades
- Describes the property as being in a highly desirable or exclusive location
- Uses phrases like "perfect for entertaining" or "slice of paradise"
- Mentions multiple positive aspects of the property in detail

Good:
- This is above Average rating but below excellent
- Uses positive descriptors like "spacious", "attractive", or "well-presented"
- Mentions desirable features like ensuite bathrooms or open plan living
- Describes the property as being in a good or popular location
- Highlights comfort and convenience
- Mentions gardens or outdoor spaces positively
- Uses phrases like "sure to impress" or "ideal family home"
- Describes multiple positive aspects, but perhaps with less enthusiasm than "Excellent" properties

Average:
- Uses moderate positive language without being overly enthusiastic
- Mentions standard features like double glazing or fitted kitchens
- Describes the property as suitable for first-time buyers or investors
- Uses phrases like "blend of convenience and comfort"
- Highlights one or two positive aspects without going into great detail
- Mentions location but doesn't emphasize it as exceptional

Below Average:
- Uses more neutral language, focusing on basic features
- Emphasizes potential rather than current condition (e.g., "investment opportunity", "further potential")
- Mentions location but doesn't describe it as particularly desirable
- Uses phrases like "cash buyers only" which might indicate issues
- Describes the property as "charming" or "Victorian" which could be euphemisms for older or outdated
- Focuses on one or two positive aspects while omitting details about others

Poor:
- Uses minimal positive language
- Focuses on very basic features or aspects (e.g., "low-maintenance garden")
- Emphasizes suitability for investors rather than homeowners
- Lacks mention of any standout features or selling points
- Uses phrases like "ideal first-time buy" without additional positive descriptors
- Provides very little detail about the property's condition or amenities

When categorizing a new property, look for the presence or absence of these indicators in the description. The more positive, superlative language and unique, desirable features mentioned, the higher the category. Conversely, descriptions that focus on basic features, potential rather than current condition, or use minimal positive language likely indicate a lower category.
"""


second_prompt = """
DESCRIPTIONS OF EACH CATEGORY

Excellent
Properties that fall into this category are described with superlative terms and showcase high-end features, exceptional presentation, and luxury elements. Keywords and phrases typically include:
    - "Beautifully presented throughout"
    - "Renovated and extended"
    - "Luxury bespoke"
    - "Exclusive and popular setting"
    - "Immaculately presented"
    - "Stunning property"
    - "Spacious executive style"
    - "Modernised throughout to a very high standard"
    - "Secluded garden"
    - "Perfect for entertaining"
    - "Ample off-road parking"
    - "Tranquil paradise"
    - "Exceptional accommodation"

Good/Above Average
These properties are often highlighted for their high functionality, attractive features, and suitability for families or first-time buyers. They are presented well but may lack the luxury or exceptional uniqueness of "Excellent" properties. Keywords and phrases typically include:
    - "Spacious lounge"
    - "Modern bathroom suite"
    - "Ideal first-time buy or investment"
    - "Executive development"
    - "Well maintained"
    - "Comfortable family home"
    - "Versatile accommodation"
    - "Open plan living space"
    - "Secure parking space"
    - "Well-maintained grounds"
    - "Desirable location"

Average
Properties in this category are typically functional and well-presented but lack distinctive features that make them stand out. They are suitable for everyday living and might appeal to first-time buyers or investors. Keywords and phrases typically include:
    - "Highly sought-after location"
    - "En-suite & a bathroom"
    - "Lounge/diner"
    - "Double glazing"
    - "Ideal choice for first-time buyers"
    - "Generous rear garden"
    - "Impressive extension"
    - "Beautifully presented"
    - "Boasts a blend of convenience and comfort"

Below Average
These properties may have potential but are often presented as opportunities for investment or require some work to reach a higher standard. They might be appealing for those looking for a project or cash buyers. Keywords and phrases typically include:
    - "Generous living space"
    - "Cash buyers only"
    - "Investment opportunity"
    - "Further potential"
    - "Charming terraced home"
    - "Victorian gem"
    - "Perfect for family living"
    - "Filled with natural light"
    - "Well-maintained"
    - "Sought-after location"
    - "Modern"

Poor
Properties classified as poor typically have minimal positive descriptions and may only appeal to first-time buyers or investors looking for low-cost options. These properties lack significant features or require substantial improvement. Keywords and phrases typically include:
    - "Low-maintenance rear garden"
    - "Ideal first-time buy or investment"
    - "Versatile property"
    - "Spacious cabin"
    - "Neutral decor"
    - "Modern"
"""


rolf_prompt = """
You are a residential property expert with 20 years of experience, specialising in analysing property descriptions to understand the condition, aesthetics and value of a property.

Do not consider anything related to the local area around a property

You will use chain of thought to complete this task.
1) I will be giving you a target property description.
2) You will need to read the description.
3) And then using the reference context (which has the full property description wording, followed by the EXTRACTED property condition describing words) I will add below, you will use the context as a reference to help you extract the property condition describing words from the target property description. ONLY extract words that relate to the property condition. Do not extract other describing words.
4) You will then reason and infer what the property condition rating and label would be, rating from 1-4 (1 is excellent condition, 4 is poor and the property requires work), and use one or more of the following labels; Excellent, Good/above average, average, below average, poor.)
5) Ensure and check your rating and condition label adheres to the information below regarding limited describing words or reference to investment or development.


PLEASE ENSURE YOU CONSIDER THE FOLLOWING:
- If the property description has very few describing words, then it probably means it is average or below, or even poor condition. Poor condition is generally ONLY for properties that are in need of work or repair.
- If the property description uses lots of words that relate to the property being a good investment, or the property has development opportunity, then it implies it is average or below, or even poor condition.
- The excellent label should only be used for the best condition properties. This is a high bar
- Do not consider anything related to the local area around a property. Do not extract or use of describing words that relate to the community or the area or location of the property


Here is the reference context:

Property 1:
Property description & features
Show home to view
Dedicated top floor principle bedroom with en suite
Two further double bedrooms
Modern family bathroom
Downstairs cloakroom
Driveway parking for two cars
* HOME TO SELL? * WE COULD BE YOUR CASH BUYER * PART EXCHANGE EVENT SATURDAY 27TH APRIL * DOORS OPEN 10AM - 5PM * *THREE STOREY* THREE BEDROOM*HUGE TOP FLOOR PRINCIPLE BEDROOM* Plot 455,The Kennett is a three storey, semi-detached home ideal for First-time buyers. Starting at on the top floor, you have the WOW factor of a huge, spacious principle bedroom, complete with en suite - you'll feel like you're on holiday everyday. With two further double bedrooms plus a family bathroom, there's no squabbling over who has what bedroom in this house. The ground floor features an open-plan kitchen / dining room with lovely French doors leading to your fully turfed garden. You'll also find a light & airy lounge with bay window, the perfect home to entertain in and be proud of. Call in & see us, or if you'd prefer make an appointment.


EXTRACTED Property 1 condition and aesthetics describing words:
- Show home
- First-time buyers.
- WOW factor
- you'll feel like you're on holiday everyday.
- the perfect home to entertain
- proud of.


Property 1 Condition rating and label
- Rating = 1
- Label = Excellent


Property 2:
Property description & features
Tenure: Freehold
Backing Onto Woodland
Annexe Potential
Solar Panels (Bought)
Three Double Bedrooms
Generous Living Space
Private Rear Garden
Virtual tour
Video Tour
DETACHED, THREE BEDROOM FAMILY HOME in the sought after suburb of Thorpe St. Andrew. With a SELF CONTAINED ANNEXE, GARAGE and plenty of living space, this property is perfect for family living. Call Sefftons TODAY to organise your viewing.


THE PROPERTY
From the central entrance hall, doors open to two well sized and bright, bay fronted double bedrooms, making use of the family bathroom.
Continuing through the hall, you are welcomed by a sizeable kitchen, ideal for hosting family and friends, and fully fitted with plenty of storage and counter space.
Additionally, there is a generous living room opening to a dining room with sliding doors to the conservatory. The property boasts ample reception space, making it ideal for family living.
Towards the rear of the property is a master bedroom filled with natural light, with French doors to the rear garden and a three piece ensuite shower room.


The property benefits from a detached, self contained annexe with a kitchen/lounge, bedroom and W.C.


OUTSIDE
To the front of the property is an extensive brick weave driveway, providing off road parking for multiple cars leading up to the detached, brick garage.
The rear garden backs onto woodland, and is lawned for the majority with shrubbery, and a patio for al fresco dining.


EXTRACTED Property 2 condition and aesthetics describing words:
- ideal for hosting family and friends
- boasts
- The lack of condition describing words suggests this property is average or below, or even poor condition


Property 2 Condition rating and label
- Rating = 3
- Label = Average or Below Average


Property 3:
Property description & features
Tenure: Freehold
CASH BUYERS ONLY
SOUGHT AFTER LOCATION
INVESTMENT OPPORTUNITY
GENEROUS REAR GARDEN
THREE BEDROOMS OFF LANDING
WITH FURTHER POTENTIAL
Virtual tour
Video Tour
CALLING ALL CASH BUYERS. This charming terraced home is IDEALLY LOCATED in the highly SOUGHT AFTER NR3 postcode. Boasting three bedrooms off of landing, and with FURTHER POTENTIAL, this property represents EXCEPTIONAL value and would be a FANTASTIC investment. Call Sefftons TODAY to organise your viewing.


THE PROPERTY
The front door opens to the covered entrance porch, leading into the generous and inviting living room, complete with feature period fireplace.
Towards the rear of the property is the well proportioned kitchen, alongside the three piece family bathroom.
Up on the first floor are three well sized bedrooms off of the landing, adding to the convenience of the property.
This home promises to be an excellent investment for those looking to create their dream home or add value to their property portfolio. Do not miss out on the chance to secure this Victorian gem and unlock its full potential.


OUTSIDE
The rear garden is generous in size, making it ideal for a keen gardener, with an outbuilding providing handy outdoor storage.


EXTRACTED Property 3 condition and aesthetics describing words:
- CASH BUYERS ONLY
- INVESTMENT OPPORTUNITY
- FURTHER POTENTIAL
- charming
- Boasting
- FURTHER POTENTIAL
- EXCEPTIONAL
- FANTASTIC
- investment.
- inviting
- feature period
-  convenience.
- excellent
- investment
- create their dream home
- add value to their property portfolio.
- Victorian
- gem
- unlock its full potential.


Property 3 Condition rating and label
- Rating = 3
- Label = Average or Below Average or Poor
"""


categorize_batch_prompt = """
You are a highly experienced real estate agent with 20 years of expertise in valuing homes based on their condition and aesthetic appeal. Your task is to critically evaluate this section of a property based on what you see.

For each image, categorize it as "internal," "external," or "floor plan." For "internal," specify the room type (e.g., living room, kitchen, bathroom, etc.). For "external," specify the exterior type (e.g., front garden, back garden, aerial view, etc.). For "floor plan," specify the plan type (e.g., ground level, site plan, etc.).

Provide clear reasons for the chosen condition label. Here's a breakdown of the different condition labels and descriptions:

Excellent:
  - High-end finishes visible (e.g., marble countertops, hardwood floors, custom cabinetry)
  - Spacious rooms with high ceilings
  - Large windows providing ample natural light
  - Modern, stylish furniture and decor
  - Luxurious amenities visible (e.g., fireplaces, chandeliers, built-in bookshelves)
  - Well-manicured landscaping or impressive outdoor spaces
  - Pool, hot tub, or other high-end outdoor features
  - Architectural details that suggest custom or designer involvement
  - Open-plan living areas with a seamless flow
  - High-quality appliances and fixtures
  - Unique design elements or layout
  - Exceptional attention to detail in staging and presentation

Good:
  - Above average quality finishes and fixtures
  - Rooms appear comfortably sized and well-proportioned
  - Good natural light
  - Furniture and decor are stylish and in good condition
  - Some desirable features visible (e.g., updated kitchen appliances, en-suite bathroom)
  - Well-maintained exterior and landscaping
  - Pleasant outdoor spaces
  - Contemporary design elements

Average:
  - Standard finishes and fixtures
  - Rooms appear adequately sized
  - Sufficient natural light
  - Furniture and decor are functional and in reasonable condition
  - Basic amenities visible (e.g., standard kitchen appliances, standard bathroom fixtures)
  - Exterior and landscaping are maintained but not exceptional
  - Typical suburban or urban setting visible in external shots

Below Average:
  - Dated or worn finishes and fixtures
  - Rooms appear small or awkwardly proportioned
  - Limited natural light
  - Furniture and decor appear outdated or in poor condition
  - Few amenities visible
  - Exterior shows signs of wear or neglect
  - Minimal or unkempt landscaping
  - Surroundings may appear less desirable in external shots

Poor:
  - Visible damage or disrepair (e.g., peeling paint, cracked tiles)
  - Rooms appear very small, cluttered, or poorly laid out
  - Little to no natural light
  - Furniture and decor (if present) are very outdated or in very poor condition
  - No visible amenities beyond absolute basics
  - Exterior shows significant wear, damage, or neglect
  - No landscaping or severely overgrown outdoor spaces
  - Surroundings appear undesirable or rundown in external shots

When categorizing a property based on images, look for these visual indicators. The more high-end features, spaciousness, natural light, and well-maintained aspects visible, the higher the category. Pay special attention to the overall aesthetic, quality of finishes, and any standout features that elevate the property above the norm.

Remember that an "Excellent" rating should be reserved for truly outstanding properties that showcase exceptional quality, design, and appeal. Don't hesitate to use this rating when a property genuinely meets these high standards.

Return the result in JSON format with an entry for each image, including the image identifier and relevant details.

Use the sample images that are shown to you to know what each category would look like.

Desired JSON format:
{
    "images": [
        {
            "image_1": {
                "category": "internal/external/floor plan",
                "details": {
                    "room_type/exterior_type/floor_type": "type based on category"
                },
                "reasoning": "Your detailed reason for the rating, highlighting specific features that influenced your decision",
                "condition": "excellent/good/average/below average/poor"
            }
        },
        ...
    ]
}
"""


labelling_prompt = """
    You are a highly experienced real estate agent with 20 years of expertise in valuing homes based on their condition and aesthetic appeal. You will be presented with a set of 5 images:

1. The first 4 images are labeled sample images representing different conditions (Excellent, Above Average, Below Average, Poor).
2. The 5th image (labeled as image number 5) is the unlabeled target image that you need to categorize.

Your task is to categorize ONLY the 5th image (image number 5) based on the criteria below and the example images provided. Do not analyze or categorize the first 4 images - they are only for reference.

Note:
- Excellent is held to a very high standard
- Above average is less than Excellent but has good to very good standard
- Critically analyze images that fall below the excellence standard to see if it is better categorized as below or above average
- Poor is held at a very low standard with a cluttered appearance and things scattered all over the place

For Interior Spaces:

Excellent:
- New or very refurbished, could be likened to a show home
- High-end, modern finishes and fixtures
- Stylish, contemporary furniture and decor
- Cohesive design with attention to detail
- Desirable features like fireplaces or built-ins
- Impeccable presentation and staging

Above Average:
- Good quality finishes and fixtures
- Well-proportioned rooms with pleasant layouts
- Attractive, well-maintained furniture and decor
- Cohesive color scheme and design
- Some desirable features
- Clean and well-presented overall

Below Average:
- Dated or worn finishes and fixtures
- Rooms may feel cramped or have awkward layouts
- Limited natural light
- Outdated or worn furniture and decor
- Lack of cohesive design or color scheme
- Few desirable features
- Signs of wear and lack of updates

Poor:
- Visible damage or disrepair
- Cramped or poorly laid out spaces
- Inadequate lighting
- Very outdated or damaged furniture and decor
- Cluttered or unkempt appearance
- No desirable features beyond basics
- Clear signs of neglect or poor maintenance

For Exterior Spaces (Front Garden and Back Garden):

Excellent:
- Professional landscaping with a variety of well-maintained plants, trees, and flowers
- High-quality hardscaping (e.g., paved pathways, patios, or decks)
- Attractive, well-maintained lawn (if present)
- Cohesive design that complements the house architecture
- Desirable features like water features, outdoor lighting, or seating areas
- Impeccable maintenance with no visible weeds or overgrowth
- For front gardens: Inviting entrance with well-maintained driveway and walkway
- For back gardens: Private, well-defined spaces for relaxation and/or entertainment

Above Average:
- Good variety of plants with evidence of regular maintenance
- Neat, well-kept lawn (if present)
- Some hardscaping elements in good condition
- Overall tidy appearance with minimal weeds
- For front gardens: Clear, welcoming path to the entrance
- For back gardens: Defined areas for different activities (e.g., dining, lounging)

Below Average:
- Limited variety of plants, some of which may be overgrown or unhealthy
- Patchy or poorly maintained lawn (if present)
- Basic or worn hardscaping
- Some visible weeds or untidy areas
- Lack of cohesive design
- For front gardens: Uninviting or unclear path to entrance
- For back gardens: Lack of defined spaces or purpose

Poor:
- Overgrown or dying plants, if any
- Neglected lawn with bare patches or dominated by weeds
- Damaged or absent hardscaping
- Cluttered with debris, excessive weeds, or unused items
- No discernible landscaping plan
- For front gardens: Unkempt appearance that detracts from the house's curb appeal
- For back gardens: Unusable or unsafe spaces with no clear purpose

When categorizing, compare the image to both these criteria and the provided sample images for each category. Pay attention to the overall quality, design, condition, and presentation of the space. Ensure your categorization aligns with the examples provided for each category.

Now categorize ONLY the 2x2 grid images in the 5th image, using the labeled images as reference examples.
Provide your analysis in the following JSON format:

{
  "images": [
    {
      "image_tag_number": int,
      "condition": string,
      "reasoning": string
    },
    {
      "image_tag_number": int,
      "condition": string,
      "reasoning": string
    },
    {
      "image_tag_number": int,
      "condition": string,
      "reasoning": string
    },
    {
      "image_tag_number": int,
      "condition": string,
      "reasoning": string
    }
  ]
}
"""
