from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
import config

def build_final_video(bg_video_path, voice_audio_path, narration_text, output_path="output/final_reels.mp4"):
    audio_clip = AudioFileClip(voice_audio_path)
    duration = audio_clip.duration
    
    video_clip = VideoFileClip(bg_video_path)
    if video_clip.duration < duration:
        video_clip = video_clip.loop(duration=duration)
    else:
        video_clip = video_clip.subclip(0, duration)
        
    video_clip = video_clip.resize(height=config.VIDEO_HEIGHT)
    if video_clip.width < config.VIDEO_WIDTH:
        video_clip = video_clip.resize(width=config.VIDEO_WIDTH)
        
    video_clip = video_clip.crop(
        x_center=video_clip.width / 2,
        y_center=video_clip.height / 2,
        width=config.VIDEO_WIDTH,
        height=config.VIDEO_HEIGHT
    ).set_audio(audio_clip)
    
    # Text Overlay Subtitle (Kuning Tebal Shadow)
    words = narration_text.split()
    chunk_size = 5
    text_chunks = [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    
    chunk_duration = duration / len(text_chunks)
    txt_clips = []
    
    for idx, chunk in enumerate(text_chunks):
        start_time = idx * chunk_duration
        txt_clip = (TextClip(chunk, 
                            fontsize=60, 
                            color='yellow', 
                            font='Arial-Bold', 
                            stroke_color='black', 
                            stroke_width=4,
                            method='caption',
                            size=(config.VIDEO_WIDTH - 120, None))
                    .set_position(('center', 'center'))
                    .set_start(start_time)
                    .set_duration(chunk_duration))
        txt_clips.append(txt_clip)
        
    final_clip = CompositeVideoClip([video_clip] + txt_clips)
    final_clip.write_videofile(
        output_path,
        fps=30,
        codec='libx264',
        audio_codec='aac',
        threads=4
    )
    return output_path