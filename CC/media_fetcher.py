import requests
import random
import os

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

def fetch_pexels_video(query, output_file="output/background.mp4"):
    """Downloads a vertical HD stock video from Pixabay API based on keyword query."""
    url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query}&video_type=film&per_page=15"
    
    response = requests.get(url)
    if response.status_code != 200:
        return fetch_pexels_video("nature", output_file)
        
    data = response.json()
    hits = data.get("hits", [])
    
    if not hits:
        return fetch_pexels_video("galaxy", output_file)
        
    selected = random.choice(hits)
    videos = selected.get("videos", {})
    
    # Pilih resolusi video HD/Medium
    video_info = videos.get("large") or videos.get("medium") or videos.get("small")
    if not video_info or "url" not in video_info:
        return fetch_pexels_video("nature", output_file)
        
    download_url = video_info["url"]
    
    video_data = requests.get(download_url).content
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "wb") as f:
        f.write(video_data)
        
    return output_file
