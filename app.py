import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

st.set_page_config(page_title="Ajay AI Creator", page_icon="🎬", layout="wide")

st.markdown("""
<style>
.stApp { background: #0b1020; color: white; }
h1, h2, h3 { color: #f4c95d; }
[data-testid="stSidebar"] { background: #151f36; }
div.stButton > button {
    background: #e7b94f; color: #111827;
    border-radius: 10px; font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🎬 Ajay AI Creator")
st.sidebar.caption("Your Personal AI Shorts Studio")
page = st.sidebar.radio(
    "MENU", ["Dashboard", "Upload Video", "Shorts & Captions", "YouTube Channels", "Schedule"]
)

def find_tool(name):
    return shutil.which(name)

def probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip())

def make_vertical_clip(source, output, start, length, progress_callback=None):
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError("Could not open the uploaded video.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError("Could not read video dimensions.")

    # Stable 9:16 canvas. Keep the complete original frame visible and preserve
    # its aspect ratio; use a soft blurred fill behind it instead of moving crops.
    height_out = height - (height % 2)
    width_out = max(2, int(height_out * 9 / 16))
    width_out -= width_out % 2
    start_frame = int(start * fps)
    frame_count = max(1, int(length * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    temp_video = str(output) + ".silent.mp4"
    writer = cv2.VideoWriter(
        temp_video, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width_out, height_out)
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not initialize video encoder.")

    for i in range(frame_count):
        ok, frame = cap.read()
        if not ok:
            break

        # Fill the portrait canvas with a blurred copy, without changing
        # the size/shape of the clear original video in the foreground.
        scale_bg = max(width_out / width, height_out / height)
        bg_w = max(width_out, int(round(width * scale_bg)))
        bg_h = max(height_out, int(round(height * scale_bg)))
        background = cv2.resize(frame, (bg_w, bg_h), interpolation=cv2.INTER_AREA)
        x_bg = max(0, (bg_w - width_out) // 2)
        y_bg = max(0, (bg_h - height_out) // 2)
        background = background[y_bg:y_bg + height_out, x_bg:x_bg + width_out]
        background = cv2.GaussianBlur(background, (0, 0), sigmaX=24, sigmaY=24)
        background = cv2.convertScaleAbs(background, alpha=0.55, beta=18)

        # Fit the full source frame inside the 9:16 canvas; never stretch it.
        scale_fg = min(width_out / width, height_out / height)
        fg_w = max(2, int(round(width * scale_fg)))
        fg_h = max(2, int(round(height * scale_fg)))
        foreground = cv2.resize(frame, (fg_w, fg_h), interpolation=cv2.INTER_AREA)
        x = (width_out - fg_w) // 2
        y = (height_out - fg_h) // 2
        background[y:y + fg_h, x:x + fg_w] = foreground
        writer.write(background)

        if progress_callback and i % max(1, frame_count // 20) == 0:
            progress_callback(i / frame_count)

    cap.release()
    writer.release()
    if not os.path.exists(temp_video) or os.path.getsize(temp_video) == 0:
        raise RuntimeError("No frames were produced from this clip.")

    mux = subprocess.run([
        "ffmpeg", "-y", "-i", temp_video, "-ss", str(start), "-i", str(source),
        "-t", str(length), "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(output)
    ], capture_output=True, text=True)
    try:
        os.remove(temp_video)
    except OSError:
        pass
    if mux.returncode != 0:
        detail = mux.stderr[-1600:] if mux.stderr else "Audio/video export failed."
        raise RuntimeError(detail)
    return True

def create_clips(source, output_dir, duration, count, progress):
    total = probe_duration(source)
    if total < 3:
        raise ValueError("This video is too short to create Shorts.")
    clip_len = min(float(duration), total)
    # Temporary candidate positions only: this is not AI viral-moment detection.
    if count == 1 or total <= clip_len:
        starts = [max(0, (total - clip_len) / 2)]
    else:
        last_start = max(0, total - clip_len)
        starts = [last_start * i / (count - 1) for i in range(count)]

    outputs = []
    for index, start in enumerate(starts, 1):
        out = Path(output_dir) / f"Ajay_Short_{index:02d}.mp4"
        make_vertical_clip(source, out, start, clip_len)
        outputs.append(out)
        progress.progress(int(index / count * 100), text=f"Creating Short {index} of {count}...")
    return outputs, total

if page == "Dashboard":
    st.title("🎬 Ajay AI Creator")
    st.subheader("Your Personal AI Shorts Studio")
    st.success("Welcome to your AI Shorts Studio!")
    col1, col2, col3 = st.columns(3)
    col1.metric("Video tools", "Ready")
    col2.metric("Individual MP4 export", "Ready")
    col3.metric("YouTube channels", "Not connected")
    st.divider()
    st.header("Start Creating")
    st.write("Upload a video you own or have permission to process.")
    st.info("Stable 9:16 framing and separate MP4 downloads are available. AI highlight selection, auto captions and YouTube publishing are not active yet.")

elif page == "Upload Video":
    st.title("📤 Upload Your Video")
    st.caption("Use videos you own or have permission to process.")
    video = st.file_uploader(
        "Choose a video", type=["mp4", "mov", "mkv", "webm"],
        help="Large uploads may still be limited by Streamlit Community Cloud memory and server limits."
    )
    if video:
        st.success(f"Selected: {video.name} ({video.size / (1024 * 1024):.1f} MB)")
        st.video(video)
        st.divider()
        st.subheader("Create vertical Shorts")
        clip_duration = st.selectbox("Length of each Short", [15, 30, 45, 60], index=1)
        clip_count = st.slider("Number of Shorts", min_value=1, max_value=10, value=3)
        st.caption("ভিডিওর পুরো আসল ফ্রেম স্থিরভাবে দেখানো হবে। কোনো মুখ-ট্র্যাকিং বা নড়াচড়া করা ক্রপ নেই; আসল ভিডিওর অনুপাতও বদলাবে না।")
        st.warning("Important: clips are still selected at evenly spaced positions. This is not AI viral analysis yet.")
        if st.button("🎬 Create Shorts", type="primary"):
            if not find_tool("ffmpeg") or not find_tool("ffprobe"):
                st.error("Video tools are not installed on the server yet.")
            else:
                work_dir = tempfile.mkdtemp(prefix="ajay_creator_")
                source_path = Path(work_dir) / Path(video.name).name
                with open(source_path, "wb") as f:
                    f.write(video.getbuffer())
                output_dir = Path(work_dir) / "shorts"
                output_dir.mkdir()
                progress = st.progress(0, text="Preparing video...")
                try:
                    outputs, total = create_clips(
                        source_path, output_dir, clip_duration, clip_count, progress
                    )
                    st.session_state["ajay_short_files"] = [str(p) for p in outputs]
                    st.session_state["ajay_short_names"] = [p.name for p in outputs]
                    st.success(f"Created {len(outputs)} individual MP4 Shorts.")
                    st.info("স্থির 9:16 ফ্রেম তৈরি হয়েছে। আসল ভিডিওটি মাঝখানে রাখা হয়েছে, তাই মুখ বা ছবি আর এদিক-ওদিক লাফাবে না।")
                except Exception as exc:
                    st.error(f"Could not create Shorts: {exc}")

        saved_files = st.session_state.get("ajay_short_files", [])
        saved_names = st.session_state.get("ajay_short_names", [])
        if saved_files:
            st.divider()
            st.subheader("Your Shorts")
            st.caption("ছোট প্রিভিউ দেখুন এবং প্রতিটি ভিডিও আলাদাভাবে MP4 হিসেবে ডাউনলোড করুন।")
            existing = [
                (idx, file_path, file_name)
                for idx, (file_path, file_name) in enumerate(zip(saved_files, saved_names), 1)
                if os.path.exists(file_path)
            ]
            # Four compact cards per row; download button sits directly below each preview.
            for row_start in range(0, len(existing), 4):
                card_columns = st.columns(4, gap="small")
                for column, item in zip(card_columns, existing[row_start:row_start + 4]):
                    idx, file_path, file_name = item
                    with column:
                        st.markdown(f"**Short {idx}**")
                        st.video(file_path)
                        with open(file_path, "rb") as f:
                            st.download_button(
                                "⬇️ Download MP4",
                                data=f.read(),
                                file_name=file_name,
                                mime="video/mp4",
                                key=f"download_short_{idx}",
                                use_container_width=True
                            )

elif page == "Shorts & Captions":
    st.title("✍️ Shorts & Captions")
    st.info("Manual caption editor is available. Automatic speech-to-text captions and AI titles/hashtags are not connected yet.")
    title = st.text_input("Shorts Title")
    caption = st.text_area("Write your caption")
    hashtags = st.text_input("Hashtags")
    if st.button("Save Draft"):
        st.session_state["ajay_draft"] = {"title": title, "caption": caption, "hashtags": hashtags}
        st.success("Draft saved in this session.")

elif page == "YouTube Channels":
    st.title("📺 YouTube Channels")
    st.warning("YouTube OAuth is not configured yet. No channel is connected and no video will be published.")
    st.write("This requires Google Cloud setup, YouTube Data API access and your explicit channel authorization.")

elif page == "Schedule":
    st.title("🗓️ Publishing Schedule")
    st.warning("Automatic YouTube scheduling is not active yet.")
    st.write("After secure channel authorization, we can add upload-and-schedule publishing.")

st.divider()
st.caption("Ajay AI Creator | Free Starter Version")
