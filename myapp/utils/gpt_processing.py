from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url
from cloudinary.api import resources_by_tag
import json
import requests
import base64
from openai import OpenAI
from typing import List, Dict, Any, Tuple, Set, Optional
import logging
from myapp.models import MenuImage
from io import BytesIO
from PIL import Image
from django.conf import settings
import time

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

client = OpenAI()

EDEN_HEADERS = {
    "Authorization": f"Bearer {settings.EDEN_API_KEY}"
}
EDEN_URL = settings.EDEN_URL
WORKFLOW_ID = settings.WORKFLOW_ID

def poll_edenai_results(execution_id: str):
    """
    Poll Eden AI for results until processing is complete.
    """
    poll_url = f"https://api.edenai.run/v2/workflow/{WORKFLOW_ID}/execution/{execution_id}/"
    for attempt in range(20):  # Poll up to 20 times
        logger.debug(f"Polling Eden AI for results (Attempt {attempt + 1})...")
        response = requests.get(poll_url, headers=EDEN_HEADERS)
        response.raise_for_status()
        data = response.json()

        status = data.get('content', {}).get('status', '')
        logger.debug(f"Current status: {status}. Full Response: {data}")

        if status in ["success", "succeeded"]:
            detected_items = []
            results = data.get('content', {}).get('results', {}).get('image__object_detection', {}).get('results', [])
            
            for provider_result in results:
                if isinstance(provider_result, dict) and 'items' in provider_result:
                    detected_items.extend(provider_result['items'])
            
            if detected_items:
                return {'items': detected_items}
            logger.error("No objects detected in successful response")
            raise Exception("No objects detected in successful response")
                
        elif status == "processing":
            time.sleep(5)
        elif status == "failed":
            errors = data.get('content', {}).get('results', {}).get('image__object_detection', {}).get('errors', [])
            error_messages = [error.get('message') for error in errors]
            logger.error(f"Workflow failed with errors: {error_messages}")
            raise Exception(f"Eden AI workflow failed: {error_messages}")
        else:
            raise Exception(f"Unexpected status: {status}")

    raise TimeoutError("Eden AI polling timed out. Results not ready.")

def process_menu_image(image_url: str, user, source_menu=None):
    """
    Process an image using Eden AI for object detection and GPT-4 for text extraction.
    Then upload the cropped sections to Cloudinary.
    """
    try:
        logger.debug(f"Starting process for image: {image_url}")
        
        # Download the image
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        image_data = BytesIO(response.content)
        logger.debug(f"Image downloaded. Size: {len(response.content)} bytes")
        image_data.seek(0)

        # Process with Eden AI
        files = {
            "file": ("image.jpg", image_data, "image/jpeg")
        }
        eden_response = requests.post(EDEN_URL, files=files, headers=EDEN_HEADERS)
        eden_response.raise_for_status()
        eden_result = eden_response.json()
        execution_id = eden_result.get('id')

        if not execution_id:
            raise Exception("Eden AI response did not return an execution ID.")

        # Get Eden AI results
        results = poll_edenai_results(execution_id)
        detected_items = results.get('items', [])
        
        if not detected_items:
            logger.error("No objects detected by Eden AI.")
            raise Exception("No objects detected by Eden AI.")

        logger.debug(f"Detected {len(detected_items)} objects.")

        # Process and upload detected objects
        extracted_images = []
        image = Image.open(BytesIO(response.content))

        for index, obj in enumerate(detected_items):
            if not obj or None in [obj.get('x_min'), obj.get('x_max'), obj.get('y_min'), obj.get('y_max')]:
                continue

            try:
                bbox = (
                    int(obj['x_min'] * image.width),
                    int(obj['y_min'] * image.height),
                    int(obj['x_max'] * image.width),
                    int(obj['y_max'] * image.height)
                )

                cropped_image = image.crop(bbox)
                buffered = BytesIO()
                cropped_image.save(buffered, format="JPEG")
                buffered.seek(0)

                # Update the folder path in the upload call
                upload_result = upload(
                    buffered,
                    folder=f"media_library/user_{user.id}/extracted",  # Changed from menu_images to media_library
                    tags=[f"user_{user.id}", "media_library", obj['label']],
                    context={"detected_as": obj['label'], "confidence": obj['confidence']}
                )

                # Save to media library with image_type='general'
                menu_image = MenuImage.objects.create(
                    user=user,
                    image=upload_result['public_id'],
                    public_id=upload_result['public_id'],
                    image_type='general',  # Changed from 'menu' to 'general'
                    menu=None  # Set to None since it's going to media library
                )

                extracted_images.append({
                    'public_id': upload_result['public_id'],
                    'url': upload_result['secure_url'],
                    'label': obj['label'],
                    'confidence': obj['confidence'],
                    'menu_image_id': menu_image.id
                })

            except Exception as crop_error:
                logger.error(f"Error processing object {index + 1}: {str(crop_error)}")
                continue

        # Process with GPT-4
        try:
            # Get menu structure and descriptions
            menu_data = process_images_with_gpt(image_url, extracted_images)
            
            if source_menu and menu_data:
                try:
                    # Match images with menu items using GPT-4V analysis
                    image_matches = match_images_to_menu_items(
                        menu_data,
                        extracted_images,
                        client
                    )

                    if image_matches:
                        # Update menu_data with image assignments
                        for category in menu_data["menu_categories"]:
                            for item in category["menu_items"]:
                                for title, image_id in image_matches:  # Now only two elements
                                    if item["title"] == title:
                                        item["matched_image_id"] = image_id
                                        # No longer trying to set match_confidence

                        # Use the parser to update the menu
                        from .parser import populate_menu_from_json
                        updated_menu = populate_menu_from_json(source_menu, menu_data)
                        logger.debug("Menu updated successfully with GPT processing results")
                        
                        return {
                            'original_image': image_url,
                            'extracted_images': extracted_images,
                            'menu_data': menu_data,
                            'menu_id': updated_menu.id,
                            'image_matches': image_matches
                        }

                except Exception as matching_error:
                    logger.error(f"Error in image matching: {str(matching_error)}")
                    
            return {
                'original_image': image_url,
                'extracted_images': extracted_images,
                'menu_data': menu_data
            }

        except Exception as gpt_error:
            logger.error(f"GPT processing failed: {str(gpt_error)}")
            return {
                'original_image': image_url,
                'extracted_images': extracted_images
            }

    except Exception as e:
        logger.error(f"Error in process_menu_image: {str(e)}")
        raise Exception(f"Error processing image: {str(e)}")


def process_images_with_gpt(image_url, individualimages = []):
    """
    Process image from Cloudinary URL using GPT-4 Vision.
    """
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        base64_image = base64.b64encode(image_data).decode('utf-8')

        Schema = '''{
            "name": "restaurant_menu",
            "schema": {
                "type": "object",
                "properties": {
                    "menu_categories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category_name": {
                                    "type": "string",
                                    "description": "The name of the category"
                                },
                                "menu_items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {
                                                "type": "string",
                                                "description": "The name of the menu item"
                                            },
                                            "description": {
                                                "type": "string",
                                                "description": "A brief description of the menu item"
                                            },
                                            "cost": {
                                                "type": "number",
                                                "description": "The price of the menu item"
                                            },
                                            "image": {
                                                "type": "string",
                                                "description": "A detailed description of any image associated with this menu item"
                                            },
                                            "options": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "option_title": {
                                                            "type": "string"
                                                        },
                                                        "pricing": {
                                                            "type": "object",
                                                            "properties": {
                                                                "additional_cost": {
                                                                    "type": "number"
                                                                },
                                                                "is_free": {
                                                                    "type": "boolean"
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }'''

        base64_image_url = f"data:image/jpeg;base64,{base64_image}"

        system_prompt = """You are an expert at analyzing menu images and providing detailed descriptions of food images. 
        When you see an image that appears to be associated with a menu item, provide a detailed description of the image 
        in the 'image' field. Focus on visual details that would help match this description with a cropped image later. 
        If no image is associated with a menu item, provide an empty string."""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Process the image according to this schema: {Schema}"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image_url,
                                "detail": "high"
                            },
                        },
                    ],
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": json.loads(Schema)
            }
        )

        response_content = response.choices[0].message.content
        menu_data = json.loads(response_content)
        return menu_data

    except Exception as e:
        raise Exception(f"Error processing image: {str(e)}")



def get_user_media_library(user_id: str) -> List[Dict[str, Any]]:
    """Get all images associated with a user from Cloudinary."""
    try:
        logger.debug(f"Fetching media library for user {user_id}")
        result = resources_by_tag(f"user_{user_id}")
        
        if not isinstance(result, dict):
            logger.warning(f"Unexpected response type from Cloudinary: {type(result)}")
            return []
        
        resources = result.get('resources', [])
        logger.debug(f"Found {len(resources)} resources")
        
        media_items = []
        for resource in resources:
            try:
                media_item = {
                    'public_id': resource.get('public_id', ''),
                    'url': resource.get('secure_url', resource.get('url', '')),
                    'created_at': resource.get('created_at', ''),
                    'tags': resource.get('tags', []),
                    'type': 'original' if 'menu_original' in resource.get('tags', []) else 'extracted',
                    'context': resource.get('context', {}),
                    'format': resource.get('format', ''),
                    'width': resource.get('width', 0),
                    'height': resource.get('height', 0)
                }
                media_items.append(media_item)
            except Exception as item_error:
                logger.error(f"Error processing media item: {str(item_error)}")
                continue
        
        return media_items
        
    except Exception as e:
        logger.error(f"Error in get_user_media_library: {str(e)}", exc_info=True)
        return []
    
def analyze_cropped_image(image_url: str, client: OpenAI) -> str:
    """
    Use GPT-4V to analyze a single cropped image and provide a detailed description.
    """
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        base64_image = base64.b64encode(image_data).decode('utf-8')
        base64_image_url = f"data:image/jpeg;base64,{base64_image}"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Provide a brief, precise description of the food item in this image. Focus only on key identifying features."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image_url,
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error analyzing cropped image: {str(e)}")
        return ""

def match_images_to_menu_items(menu_data: Dict, extracted_images: List[Dict], client: OpenAI) -> List[Tuple[str, str]]:
    """
    Match extracted images to menu items using GPT-4V analysis.
    For each menu item with an image description, finds the best match from remaining images.
    """
    # First, get descriptions for all extracted images
    available_images = {}
    for image in extracted_images:
        try:
            description = analyze_cropped_image(image['url'], client)
            available_images[image['public_id']] = {
                'description': description,
                'url': image['url']
            }
        except Exception as e:
            logger.error(f"Error analyzing image {image['public_id']}: {str(e)}")
            continue

    matches = []
    
    # Process each menu item
    for category in menu_data.get("menu_categories", []):
        for item in category.get("menu_items", []):
            if not item.get("image") or not available_images:  # Skip if no image description or no images left
                continue

            prompt = f"""Based on the descriptions, which of these images best matches this menu item?
            
            MENU ITEM:
            {item['title']}
            Description: {item['image']}
            
            AVAILABLE IMAGES:
            {', '.join(f'{id}: {info["description"]}' for id, info in available_images.items())}
            
            INSTRUCTIONS:
            - Return ONLY the image ID that best matches
            - If no good match exists, return NONE
            - Do not include any explanation or additional text"""

            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a precise image matching assistant. Respond only with the exact ID of the best matching image or NONE if no good match exists."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=100
                )
                
                # Get the response and clean it
                matched_image_id = response.choices[0].message.content.strip()
                
                # Remove any extra text/punctuation that might have been included
                for image_id in available_images.keys():
                    if image_id in matched_image_id:
                        matched_image_id = image_id
                        break
                else:
                    continue  # No valid image ID found in response
                
                # If we found a valid match
                if matched_image_id in available_images:
                    matches.append((item['title'], matched_image_id))
                    # Remove the matched image from available pool
                    del available_images[matched_image_id]
                    logger.info(f"Matched image {matched_image_id} to menu item {item['title']}")
                
            except Exception as e:
                logger.error(f"Error matching image for {item['title']}: {str(e)}")
                continue

    return matches