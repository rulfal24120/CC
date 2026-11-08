import random
import json
import os
from pytrends.request import TrendReq

def get_trending_topic() -> str:
    """
    Mengambil topik tren dari Google Trends (region US).
    Jika terjadi rate limit/error, otomatis mengambil dari config/topics.json.
    """
    try:
        pytrends = TrendReq(hl='en-US', tz=300, timeout=(5, 10))
        # Mengambil trending searches terkini di US
        df = pytrends.trending_searches(pn='united_states')
        trending_list = df[0].tolist()
        if trending_list:
            selected_topic = random.choice(trending_list[:10])
            print(f"[TrendFinder] Berhasil mengambil topik tren Google: {selected_topic}")
            return selected_topic
    except Exception as e:
        print(f"[TrendFinder] Pytrends error/blocked ({e}). Menggunakan fallback topics.json...")

    # Fallback Mechanism
    config_path = os.path.join("config", "topics.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            topics = json.load(f)
            selected_topic = random.choice(topics)
            print(f"[TrendFinder] Menggunakan topik fallback: {selected_topic}")
            return selected_topic
    
    return "Surprising psychology facts about human behavior"
