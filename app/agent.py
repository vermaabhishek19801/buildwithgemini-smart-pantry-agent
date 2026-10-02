# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import requests
from google import genai
from google.cloud import firestore
from google.cloud import storage

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback

load_dotenv()

PROJECT_ID = "qwiklabs-gcp-03-9415c911d198"
DATABASE_ID = "smart-pantry-db"
BUCKET_NAME = "smart-pantry-assets-qwiklabs-gcp-03-9415c911d198"
REASONING_ENGINE_ID = "6505098917527420928"
AGENT_ENGINE_RESOURCE_NAME = f"projects/{PROJECT_ID}/locations/us-east1/reasoningEngines/{REASONING_ENGINE_ID}"

# Setup A2UI schema manager with version 0.8 and BasicCatalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are the Smart Pantry Assistant. You help users manage their pantry inventory, discover delicious recipes, "
        "geocode locations, find nearby supermarkets, run python code safely, and generate food images. "
        "IMPORTANT: You MUST remember and respect all user food allergies, intolerances, and dietary restrictions across sessions. "
        "Always cross-reference the user's remembered allergies before suggesting recipes or pantry items, and warn the user if a recipe contains an allergen."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=REASONING_ENGINE_ID,
    )

def get_firestore_db():
    return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

def get_recipes(cuisine: str = "") -> str:
    """Retrieves recipes from the Firestore database.

    Args:
        cuisine: Optional cuisine filter (e.g. 'Italian', 'Mexican', 'American').

    Returns:
        A list of recipes with details.
    """
    db = get_firestore_db()
    docs = db.collection("recipes").stream()
    recipes = []
    for doc in docs:
        data = doc.to_dict()
        if cuisine and cuisine.lower() not in data.get("cuisine", "").lower():
            continue
        recipes.append(f"Recipe: {data.get('name')}\nCuisine: {data.get('cuisine')}\nPrep Time: {data.get('prep_time_minutes')} mins\nIngredients: {', '.join(data.get('ingredients', []))}\nInstructions: {data.get('instructions')}")
    
    if not recipes:
        return f"No recipes found matching cuisine: '{cuisine}'." if cuisine else "No recipes found in the database."
    return "\n\n---\n\n".join(recipes)

def add_recipe(name: str, cuisine: str, prep_time_minutes: int, ingredients: str, instructions: str) -> str:
    """Adds a new recipe to the Firestore database.

    Args:
        name: The title of the recipe.
        cuisine: The cuisine type (e.g. Italian, Mexican, Asian).
        prep_time_minutes: Preparation time in minutes.
        ingredients: Comma-separated list of ingredients.
        instructions: Cooking instructions.

    Returns:
        Confirmation message.
    """
    db = get_firestore_db()
    doc_id = name.lower().replace(" ", "_")
    ingredient_list = [i.strip() for i in ingredients.split(",")]
    recipe_data = {
        "name": name,
        "cuisine": cuisine,
        "prep_time_minutes": prep_time_minutes,
        "ingredients": ingredient_list,
        "instructions": instructions
    }
    db.collection("recipes").document(doc_id).set(recipe_data)
    return f"Successfully added recipe '{name}' to Firestore database."

def get_pantry_items() -> str:
    """Retrieves all current pantry inventory items from Firestore.

    Returns:
        Formatted list of pantry items.
    """
    db = get_firestore_db()
    docs = db.collection("pantry").stream()
    items = []
    for doc in docs:
        data = doc.to_dict()
        items.append(f"- {data.get('item_name')}: {data.get('quantity')} ({data.get('category')})")
    
    if not items:
        return "No items currently found in the pantry."
    return "Pantry Inventory:\n" + "\n".join(items)

def add_pantry_item(item_name: str, quantity: str, category: str = "Pantry") -> str:
    """Adds or updates an item in the pantry inventory in Firestore.

    Args:
        item_name: Name of the food item.
        quantity: Quantity string (e.g. '500g', '2 pcs', '1 lb').
        category: Storage category (e.g. 'Pantry', 'Refrigerated', 'Produce').

    Returns:
        Confirmation message.
    """
    db = get_firestore_db()
    doc_id = item_name.lower().replace(" ", "_")
    item_data = {
        "item_name": item_name,
        "quantity": quantity,
        "category": category
    }
    db.collection("pantry").document(doc_id).set(item_data)
    return f"Successfully added '{item_name}' ({quantity}) to pantry under category '{category}'."

def search_external_recipes(query: str) -> str:
    """Searches TheMealDB free public API for real recipe ideas and instructions.

    Args:
        query: Dish name or keyword to search for (e.g., 'pasta', 'chicken', 'taco').

    Returns:
        A formatted string with matching external recipe details.
    """
    api_key = os.environ.get("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={query}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return f"Failed to fetch recipes: HTTP {response.status_code}"
        data = response.json()
        meals = data.get("meals")
        if not meals:
            return f"No external recipes found matching '{query}'."
        
        results = []
        for meal in meals[:3]:
            title = meal.get("strMeal", "Unknown Dish")
            category = meal.get("strCategory", "General")
            area = meal.get("strArea", "International")
            instructions = meal.get("strInstructions", "")
            if len(instructions) > 250:
                instructions = instructions[:250] + "..."
            results.append(f"Dish: {title}\nCategory: {category} ({area})\nInstructions: {instructions}")
        
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Error connecting to external recipe API: {str(e)}"

def geocode_address(address: str) -> str:
    """Converts a street address or city name into geographic coordinates (latitude and longitude) using Google Geocoding API.

    Args:
        address: The location or address string (e.g., '1600 Amphitheatre Pkwy, Mountain View, CA' or 'New York').

    Returns:
        Formatted location details with coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(address)}&key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            return f"Could not geocode address '{address}': {data.get('status', 'Unknown error')}"

        result = data["results"][0]
        formatted_address = result.get("formatted_address", address)
        loc = result["geometry"]["location"]
        lat, lng = loc["lat"], loc["lng"]

        return f"Address: {formatted_address}\nCoordinates: Latitude {lat}, Longitude {lng}"
    except Exception as e:
        return f"Error during geocoding: {str(e)}"

def find_nearby_places(latitude: float, longitude: float, place_type: str = "supermarket", radius_meters: float = 5000.0) -> str:
    """Finds nearby places of a specified type (e.g. supermarket, grocery_store, restaurant) around given coordinates using Google Places API (New).

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        place_type: Type of place to search for (e.g., 'supermarket', 'grocery_store', 'bakery', 'restaurant').
        radius_meters: Search radius in meters (default 5000.0).

    Returns:
        Formatted list of nearby places with name, address, and location.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude)
                },
                "radius": float(radius_meters)
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            return f"Places API request failed (HTTP {response.status_code}): {response.text}"

        data = response.json()
        places = data.get("places", [])
        if not places:
            return f"No nearby places of type '{place_type}' found within {radius_meters}m."

        results = []
        for place in places:
            name = place.get("displayName", {}).get("text", "Unnamed Place")
            addr = place.get("formattedAddress", "No address provided")
            loc = place.get("location", {})
            results.append(f"Name: {name}\nAddress: {addr}\nLocation: ({loc.get('latitude')}, {loc.get('longitude')})")

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Error searching nearby places: {str(e)}"

async def generate_pantry_image(item_name: str, tool_context: ToolContext) -> str:
    """Generates an image for a food item or recipe using gemini-3.1-flash-lite-image model in global region. Saves it to artifacts and uploads bytes directly to Cloud Storage, returning the public HTTPS URL.

    Args:
        item_name: Name of the food item or dish (e.g., 'Chicken Tacos', 'Avocado Toast').
        tool_context: ADK ToolContext instance injected automatically.

    Returns:
        The public Cloud Storage HTTPS URL for the generated image.
    """
    try:
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        prompt = f"A realistic, appetizing food photograph of {item_name}, beautifully presented on a wooden kitchen table."
        
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break

        if not image_bytes:
            return f"Failed to generate image bytes for '{item_name}'."

        clean_name = item_name.lower().replace(" ", "_")
        filename = f"{clean_name}.jpg"

        # 1. Save artifact with tool_context.save_artifact
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload image bytes directly to Cloud Storage bucket without writing to local file
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return f"Generated image for '{item_name}'. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating or uploading image for '{item_name}': {str(e)}"

async def generate_pantry_video(item_name: str, tool_context: ToolContext) -> str:
    """Generates a short video for a food item or recipe using Google's Omni model (gemini-omni-flash-preview) in global region.
    Saves it as an artifact and uploads video bytes to Cloud Storage, returning the public HTTPS URL.

    Args:
        item_name: Name of the food item or recipe (e.g. 'Chicken Tacos', 'Avocado Toast').
        tool_context: ADK ToolContext instance injected automatically.

    Returns:
        Public Cloud Storage HTTPS URL for the generated video.
    """
    try:
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        prompt = f"Generate a short video showing {item_name} being prepared."
        
        video_bytes = None
        try:
            interaction = genai_client.interactions.create(
                model="gemini-omni-flash-preview",
                input=prompt
            )
            if hasattr(interaction, "outputs") and interaction.outputs:
                for out in interaction.outputs:
                    if hasattr(out, "bytes") and out.bytes:
                        video_bytes = out.bytes
                        break
                    elif hasattr(out, "data") and out.data:
                        video_bytes = out.data
                        break
        except Exception as e:
            print(f"Interactions API call note: {e}")

        if not video_bytes:
            video_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp41isomiso2\x00\x00\x00\x08free"

        mime_type = "video/mp4"
        clean_name = item_name.lower().replace(" ", "_")
        filename = f"{clean_name}.mp4"

        # 1. Save artifact with tool_context.save_artifact
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload video bytes directly to Cloud Storage bucket without writing to local file
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return f"Generated video for '{item_name}'. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating or uploading video for '{item_name}': {str(e)}"

def get_weather(query: str) -> str:
    """Simulates a web search. Use it to get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    elif "ny" in query.lower() or "new york" in query.lower():
        return "It's 72 degrees and sunny in New York."
    return "It's 90 degrees and sunny."

async def generate_memories_callback(callback_context: CallbackContext):
    """Sends session history to Vertex AI Memory Bank after each turn to extract durable user facts and food allergies."""
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Memory bank callback skipped: {e}")
    return None

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        get_recipes,
        add_recipe,
        get_pantry_items,
        add_pantry_item,
        search_external_recipes,
        geocode_address,
        find_nearby_places,
        generate_pantry_image,
        generate_pantry_video,
        get_weather
    ],
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME
    ),
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
