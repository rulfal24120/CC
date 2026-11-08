import os
import json
from google import genai
from google.genai import types

def generate_script_and_metadata(topic: str) -> dict:
    """
    Menghasilkan naskah, query visual Pixabay, judul, deskripsi, dan tags
    berformat JSON terstruktur menggunakan Gemini API.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY tidak ditemukan di environment variable.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are an expert short-form content creator targeting a US audience on YouTube Shorts and Instagram Reels.
    Create an engaging 30-second video script about the topic: "{topic}".

    Requirements:
    1. Language: English (US).
    2. Hook: Highly engaging hook in the first 3 seconds.
    3. Voiceover script text: Clear, punchy, include proper commas and periods for natural speech pauses.
    4. Pixabay query: 2-4 general English keywords for vertical stock videos (e.g., "dark moody nature", "cinematic city night", "abstract brain animation").
    5. Title: Catchy title under 60 characters with 1 hashtag.
    6. Description: Engaging 2-line text + Call to Action + 5 viral hashtags (#shorts #reels #psychology etc.).
    7. Tags: Array of 10 relevant tags.

    Return strictly a raw JSON object with this key structure:
    {{
      "topic": "{topic}",
      "pixabay_search_query": "string",
      "script_text": "string",
      "metadata": {{
        "title": "string",
        "description": "string",
        "tags": ["tag1", "tag2"],
        "hashtags": ["#tag1", "#tag2"]
      }}
    }}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    data = json.loads(response.text)
    print(f"[ScriptGenerator] Berhasil membuat naskah & metadata untuk topik: {topic}")
    return data
