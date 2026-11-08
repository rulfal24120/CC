import os
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeAudioFileClip, 
    TextClip, CompositeVideoClip, vfx
)

def compile_video(
    video_path: str, 
    voice_path: str, 
    bgm_path: str, 
    script_text: str, 
    output_path: str
) -> str:
    """
    Menggabungkan video, voiceover, BGM tipis, dan subtitle ke file MP4 final 720p.
    """
    print("[VideoCompiler] Memulai rendering video...")

    voice_clip = AudioFileClip(voice_path)
    audio_duration = voice_clip.duration

    video_clip = VideoFileClip(video_path)
    if video_clip.duration < audio_duration:
        video_clip = video_clip.fx(vfx.loop, duration=audio_duration)
    else:
        video_clip = video_clip.subclip(0, audio_duration)

    video_clip = video_clip.resize(newsize=(720, 1280))

    audio_tracks = [voice_clip]
    if os.path.exists(bgm_path):
        bgm_clip = AudioFileClip(bgm_path).volumex(0.12)
        if bgm_clip.duration < audio_duration:
            bgm_clip = bgm_clip.fx(vfx.loop, duration=audio_duration)
        else:
            bgm_clip = bgm_clip.subclip(0, audio_duration)
        audio_tracks.append(bgm_clip)

    final_audio = CompositeAudioFileClip(audio_tracks)
    video_clip = video_clip.set_audio(final_audio)

    try:
        subtitle_clip = TextClip(
            script_text, 
            fontsize=32, 
            color='yellow', 
            font='DejaVu-Sans-Bold', 
            stroke_color='black', 
            stroke_width=2,
            method='caption',
            size=(640, None)
        ).set_position(('center', 'center')).set_duration(audio_duration)
        
        final_clip = CompositeVideoClip([video_clip, subtitle_clip])
    except Exception as e:
        print(f"[VideoCompiler] Subtitle fallback: {e}")
        final_clip = video_clip

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_clip.write_videofile(
        output_path,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='ultrafast',
        threads=2
    )

    voice_clip.close()
    video_clip.close()
    final_clip.close()

    print(f"[VideoCompiler] Rendering selesai: {output_path}")
    return output_path
