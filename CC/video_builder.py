import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip
import config

def create_subtitle_image(text, width=960, font_size=55, color="yellow", stroke_color="black", stroke_width=4):
    """Membuat gambar subtitle transparan menggunakan PIL tanpa butuh ImageMagick."""
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
        
    wrapped_text = '\n'.join(lines)
    
    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
    text_w = int(bbox[2] - bbox[0] + (stroke_width * 4))
    text_h = int(bbox[3] - bbox[1] + (stroke_width * 4))
    
    text_w = max(1, text_w)
    text_h = max(1, text_h)
    
    img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    draw.multiline_text(
        (text_w // 2, text_h // 2),
        wrapped_text,
        font=font,
        fill=color,
        anchor="mm",
        align="center",
        stroke_width=stroke_width,
        stroke_fill=stroke_color
    )
    
    return np.array(img)

def build_final_video(bg_video_path, voice_audio_path, narration_text, output_path="output/final_reels.mp4"):
    audio_clip = AudioFileClip(voice_audio_path)
    duration = audio_clip.duration
    
    video_clip = VideoFileClip(bg_video_path)
    if video_clip.duration < duration:
        video_clip = video_clip.loop(duration=duration)
    else:
        video_clip = video_clip.subclip(0, duration)
        
    video_clip = video_clip.resize(height=config.VIDEO_HEIGHT)
    if video_clip.w < config.VIDEO_WIDTH:
        video_clip = video_clip.resize(width=config.VIDEO_WIDTH)
        
    video_clip = video_clip.crop(
        x_center=video_clip.w / 2,
        y_center=video_clip.h / 2,
        width=config.VIDEO_WIDTH,
        height=config.VIDEO_HEIGHT
    ).set_audio(audio_clip)
    
    words = narration_text.split()
    chunk_size = 5
    text_chunks = [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    
    chunk_duration = duration / len(text_chunks)
    txt_clips = []
    
    # Menentukan posisi vertikal di 75% dari atas layar (posisi bawah yang ideal)
    subtitle_y_position = int(config.VIDEO_HEIGHT * 0.75)
    
    for idx, chunk in enumerate(text_chunks):
        start_time = idx * chunk_duration
        img_np = create_subtitle_image(chunk, width=config.VIDEO_WIDTH - 120)
        
        txt_clip = (ImageClip(img_np)
                    .set_position(('center', subtitle_y_position))
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
