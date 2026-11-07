import os
import json
import config
from script_generator import generate_script
from voice_generator import generate_voiceover
from media_fetcher import fetch_pexels_video
from video_builder import build_final_video

def run_pipeline():
    print("=== STARTING AUTOMATED CONTENT PIPELINE ===")
    
    # 1. Generate Script, Title, Caption & Hashtags
    print("[1/5] Generating Script, Caption & Hashtags via Gemini...")
    script_data = generate_script()
    print(f"Topic Keyword: {script_data.get('topic_query')}")
    print(f"Title: {script_data.get('title')}")
    
    # Simpan Metadata (Caption + Hashtags) ke file teks agar mudah di-copy saat upload
    metadata_path = os.path.join(config.OUTPUT_DIR, "metadata.txt")
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write(f"JUDUL:\n{script_data.get('title')}\n\n")
        f.write(f"CAPTION:\n{script_data.get('caption')}\n\n")
        f.write(f"HASHTAGS:\n{script_data.get('hashtags')}\n")
        
    # Simpan juga sebagai JSON untuk kemudahan integrasi bot/webhook mendatang
    json_path = os.path.join(config.OUTPUT_DIR, "metadata.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    
    # 2. Generate Voiceover Audio
    print("[2/5] Generating Voiceover...")
    voice_path = os.path.join(config.OUTPUT_DIR, "voiceover.mp3")
    generate_voiceover(script_data['narration'], voice_path)
    
    # 3. Fetch Background Video
    print("[3/5] Fetching Background Video...")
    bg_path = os.path.join(config.OUTPUT_DIR, "background.mp4")
    fetch_pexels_video(script_data.get('topic_query', 'nature'), bg_path)
    
    # 4. Build Final Video with Subtitles
    print("[4/5] Building Final Video...")
    final_video = os.path.join(config.OUTPUT_DIR, "final_reels.mp4")
    build_final_video(bg_path, voice_path, script_data['narration'], final_video)
    
    print("[5/5] Content Artifacts Ready in Output Folder!")
    print("=== PIPELINE EXECUTION COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_pipeline()
