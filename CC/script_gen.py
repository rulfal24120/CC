import json
from google import genai
import config

def generate_fact_script():
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    prompt = """
    You are a viral content creator targeting a US audience.
    Generate a 30-second "Daily Mind-Blowing Fun Fact or News Story".
    
    Requirements:
    1. Strong visual hook in the first 3 seconds (e.g. "If you live in the US, you need to know this...").
    2. Engaging narration text (around 50-65 words).
    3. 3-4 simple English keywords to search for relevant stock background videos (e.g. "space galaxy", "city night", "dark ocean").
    
    Output strictly in JSON format without markdown formatting:
    {
        "title": "Short catchy title",
        "narration": "Full narration text to be spoken by AI voice...",
        "keywords": ["keyword1", "keyword2", "keyword3"],
        "caption": "Full Instagram/Shorts caption with trending hashtags #FunFacts #DidYouKnow #MindBlowing #USNews"
    }
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
        
    return json.loads(raw_text.strip())