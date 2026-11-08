import os
import shutil
from src.trend_finder import get_trending_topic
from src.script_generator import generate_script_and_metadata
from src.audio_generator import generate_audio
from src.visual_fetcher import fetch_background_video
from src.video_compiler import compile_video
from src.telegram_notifier import send_telegram_notification

def cleanup_previous_production():
    """
    Menghapus folder temp & output lama SEBELUM produksi baru dimulai.
    """
    dirs_to_clean = ["assets_temp", "output"]
    for d in dirs_to_clean:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[Orchestrator] Membersihkan direktori lama: {d}")
        os.makedirs(d, exist_ok=True)

def main():
    print("==================================================")
    print("      MEMULAI PRODUKSI PABRIK KONTEN REELS       ")
    print("==================================================")

    cleanup_previous_production()

    temp_dir = "assets_temp"
    output_dir = "output"
    
    audio_path = os.path.join(temp_dir, "voice.mp3")
    bg_video_path = os.path.join(temp_dir, "background.mp4")
    bgm_path = os.path.join("assets", "bgm.mp3")
    final_video_path = os.path.join(output_dir, "final_reels.mp4")

    topic = get_trending_topic()
    script_data = generate_script_and_metadata(topic)
    script_text = script_data.get("script_text", "")
    pixabay_query = script_data.get("pixabay_search_query", "cinematic nature")
    metadata = script_data.get("metadata", {})

    generate_audio(script_text, audio_path)
    fetch_background_video(pixabay_query, bg_video_path)
    compile_video(bg_video_path, audio_path, bgm_path, script_text, final_video_path)
    send_telegram_notification(final_video_path, metadata)

    print("==================================================")
    print("     PRODUKSI SELESAI & VIDEO SIAP DIUNGGAH       ")
    print("==================================================")

if __name__ == "__main__":
    main()
