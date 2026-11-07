import requests
import random
import config

def fetch_pexels_video(query, output_file="output/background.mp4"):
    url = f"[https://api.pexels.com/videos/search?query=](https://api.pexels.com/videos/search?query=){query}&per_page=15&orientation=portrait"
    headers = {"Authorization": config.PEXELS_API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return fetch_pexels_video("nature", output_file)
        
    data = response.json()
    videos = data.get("videos", [])
    
    if not videos:
        return fetch_pexels_video("dark space", output_file)
        
    selected_video = random.choice(videos)
    video_files = selected_video.get("video_files", [])
    
    download_url = None
    for file in video_files:
        if file.get("height", 0) > file.get("width", 0):
            download_url = file["link"]
            break
            
    if not download_url and video_files:
        download_url = video_files[0]["link"]
        
    video_data = requests.get(download_url).content
    with open(output_file, "wb") as f:
        f.write(video_data)
        
    return output_file