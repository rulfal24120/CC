import os
import json
import re
from google import genai
import config

def generate_script():
    """Menggenerate Naskah, Judul, Caption, dan Hashtag dari Gemini API."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    prompt = """
    Buatkan 1 paket konten video pendek (Reels/Shorts) berbahasa Indonesia yang menarik dan edukatif.
    
    Kembalikan respon HANYA dalam format JSON valid tanpa format markdown dengan struktur:
    {
      "topic_query": "kata kunci 1-2 kata bahasa inggris untuk cari video b-roll di pixabay (misal: nature, galaxy, runner, coffee)",
      "title": "Judul menarik maksimal 6 kata",
      "narration": "Teks naskah dubbing suara durasi 15-30 detik. Jangan gunakan simbol aneh.",
      "caption": "Deskripsi caption Instagram/YouTube yang memancing interaksi penonton.",
      "hashtags": "5-8 hashtag populer dan relevan yang dipisahkan spasi"
    }
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    text_response = response.text.strip()
    text_response = re.sub(r'^```json\s*', '', text_response)
    text_response = re.sub(r'^```\s*', '', text_response)
    text_response = re.sub(r'\s*```$', '', text_response)
    
    try:
        data = json.loads(text_response)
    except Exception:
        data = {
            "topic_query": "nature",
            "title": "Tips Hari Ini",
            "narration": "Tetap semangat menjalani hari ini dan pastikan kamu terus berusaha mencapai tujuanmu.",
            "caption": "Semoga menyemangati harimu! Jangan lupa follow untuk tips harian lainnya.",
            "hashtags": "#motivation #reels #shorts #life #inspiration"
        }
        
    return data
