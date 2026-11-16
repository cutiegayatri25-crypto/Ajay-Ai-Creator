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

def detect_face_center(frame, detector):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(
        gray, scaleFactor=1.15, minNeighbors=4, minSize=(35, 35)
    )
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
    return x + w // 2

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

    crop_width = min(width, max(2, int(height * 9 / 16)))
    crop_width -= crop_width % 2
    height_out = height - (height % 2)
    width_out = crop_width
    start_frame = int(start * fps)
    frame_count = max(1, int(length * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    temp_video = str(output) + ".silent.mp4"
    writer = cv2.VideoWriter(
        temp_video, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width_out, height_out)
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not initialize video encoder.")

    last_center = width // 2
    detected_any = False
    for i in range(frame_count):
        ok, frame = cap.read()
        if not ok:
            break
        # Face detection on every 5th frame keeps processing lighter.
        if i % 5 == 0:
            face_center = detect_face_center(frame, detector)
            if face_center is not None:
                last_center = int(0.65 * last_center + 0.35 * face_center)
                detected_any = True

        left = max(0, min(width - crop_width, last_center - crop_width // 2))
        cropped = frame[0:height_out, left:left + crop_width]
        if cropped.shape[1] != crop_width:
            cropped = cv2.resize(cropped, (crop_width, height_out))
        writer.write(cropped)

        if progress_callback and i % max(1, frame_count // 20) == 0:
            progress_callback(i / frame_count)

    cap.release()
    writer.release()
    if not os.path.exists(temp_video) or os.path.getsize(temp_video) == 0:
        raise RuntimeError("No frames were produced from this clip.")

    # Copy original audio into the newly framed vertical video.
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
    return detected_any

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
    any_face = False
    for index, start in enumerate(starts, 1):
        out = Path(output_dir) / f"Ajay_Short_{index:02d}.mp4"
        detected = make_vertical_clip(source, out, start, clip_len)
        any_face = any_face or detected
        outputs.append(out)
        progress.progress(int(index / count * 100), text=f"Creating Short {index} of {count}...")
    return outputs, total, any_face

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
    st.info("Face-aware framing and separate MP4 downloads are available in this build. AI viral-moment selection, auto captions and YouTube publishing are not active yet.")

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
        st.caption("The app will try to keep a detected face near the center. If no face is detected, it uses the center of the frame.")
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
                    outputs, total, face_found = create_clips(
                        source_path, output_dir, clip_duration, clip_count, progress
                    )
                    st.session_state["ajay_short_files"] = [str(p) for p in outputs]
                    st.session_state["ajay_short_names"] = [p.name for p in outputs]
                    st.session_state["ajay_face_detected"] = face_found
                    st.success(f"Created {len(outputs)} individual MP4 Shorts.")
                    if face_found:
                        st.info("A face was detected in at least part of the video; the crop was adjusted to follow it.")
                    else:
                        st.warning("No clear face was detected. Center framing was used; please check the preview.")
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
