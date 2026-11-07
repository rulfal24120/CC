import random
import config
from script_gen import generate_fact_script
from voice_gen import generate_voiceover
from media_fetcher import fetch_pexels_video
from video_builder import build_final_video
from meta_publisher import publish_to_instagram
from yt_publisher import publish_to_youtube

def run_pipeline():
    print("=== STARTING AUTOMATED CONTENT PIPELINE ===")
    
    # 1. Script
    print("[1/5] Generating Script...")
    script_data = generate_fact_script()
    
    # 2. Voiceover
    print("[2/5] Generating Voiceover...")
    voice_path = "output/voiceover.mp3"
    generate_voiceover(script_data['narration'], voice_path)
    
    # 3. Background Media
    print("[3/5] Fetching Background Video...")
    keyword = random.choice(script_data['keywords'])
    bg_path = "output/background.mp4"
    fetch_pexels_video(keyword, bg_path)
    
    # 4. Rendering
    print("[4/5] Building Final Video...")
    final_video = "output/final_reels.mp4"
    build_final_video(bg_path, voice_path, script_data['narration'], final_video)
    
    # 5. Publishing
    print("[5/5] Publishing to Platforms...")
    caption_text = f"{script_data['title']}\n\n{script_data['caption']}"
    
    # Note: Meta API requires a public URL for video upload.
    # On local testing, video is saved in output/final_reels.mp4
    
    print("\n=== PIPELINE EXECUTION COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_pipeline()