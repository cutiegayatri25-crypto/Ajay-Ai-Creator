import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Ajay AI Creator",
    page_icon="🎬",
    layout="wide"
)

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
    "MENU",
    ["Dashboard", "Upload Video", "Shorts & Captions", "YouTube Channels", "Schedule"]
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

def create_shorts(source_path, output_dir, duration, count):
    total = probe_duration(source_path)
    if total < 3:
        raise ValueError("This video is too short to create Shorts.")

    clip_len = min(float(duration), total)
    # Spread clips across the full video instead of taking only its beginning.
    if count == 1 or total <= clip_len:
        starts = [max(0, (total - clip_len) / 2)]
    else:
        last_start = max(0, total - clip_len)
        starts = [last_start * i / (count - 1) for i in range(count)]

    made = []
    for index, start in enumerate(starts, 1):
        out = Path(output_dir) / f"Ajay_Short_{index:02d}.mp4"
        command = [
            "ffmpeg", "-y", "-ss", str(start), "-i", str(source_path),
            "-t", str(clip_len),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero", str(out)
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr[-1800:] if result.stderr else "Unknown FFmpeg error"
            raise RuntimeError(detail)
        made.append(out)
    return made, total

if page == "Dashboard":
    st.title("🎬 Ajay AI Creator")
    st.subheader("Your Personal AI Shorts Studio")
    st.success("Welcome to your AI Shorts Studio!")
    col1, col2, col3 = st.columns(3)
    col1.metric("Video tools", "Ready")
    col2.metric("Shorts export", "Ready")
    col3.metric("YouTube channels", "Not connected")
    st.divider()
    st.header("Start Creating")
    st.write("Upload an authorized video, choose clip settings, and create vertical Shorts.")
    st.info("Automatic AI highlight detection, captions, channel connection and publishing are still under development.")

elif page == "Upload Video":
    st.title("📤 Upload Your Video")
    st.caption("Use videos you own or have permission to process.")
    video = st.file_uploader(
        "Choose a video",
        type=["mp4", "mov", "mkv", "webm"],
        help="Large uploads may be limited by Streamlit Community Cloud memory and server limits."
    )

    if video:
        st.success(f"Selected: {video.name} ({video.size / (1024 * 1024):.1f} MB)")
        st.video(video)
        st.divider()
        st.subheader("Create vertical Shorts")
        clip_duration = st.selectbox("Length of each Short", [15, 30, 45, 60], index=1)
        clip_count = st.slider("Number of Shorts", min_value=1, max_value=10, value=3)
        st.caption("This starter version makes evenly spaced clips. It does not yet use AI to detect the most engaging moments.")
        if st.button("🎬 Create Shorts", type="primary"):
            if not find_tool("ffmpeg") or not find_tool("ffprobe"):
                st.error("Video tools are not installed on the server yet. Please try again later.")
            else:
                progress = st.progress(0, text="Preparing video...")
                try:
                    work_dir = tempfile.mkdtemp(prefix="ajay_creator_")
                    source_path = Path(work_dir) / Path(video.name).name
                    with open(source_path, "wb") as f:
                        f.write(video.getbuffer())
                    output_dir = Path(work_dir) / "shorts"
                    output_dir.mkdir()
                    progress.progress(15, text="Reading video...")
                    made, total = create_shorts(source_path, output_dir, clip_duration, clip_count)
                    progress.progress(85, text="Packing Shorts...")
                    zip_path = Path(work_dir) / "Ajay_AI_Creator_Shorts.zip"
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                        for clip in made:
                            archive.write(clip, arcname=clip.name)
                    st.session_state["ajay_shorts_zip"] = str(zip_path)
                    st.session_state["ajay_shorts_count"] = len(made)
                    st.session_state["ajay_shorts_duration"] = total
                    progress.progress(100, text="Finished!")
                    st.success(f"Created {len(made)} vertical Shorts.")
                except Exception as exc:
                    st.error(f"Could not create Shorts: {exc}")
        zip_saved = st.session_state.get("ajay_shorts_zip")
        if zip_saved and os.path.exists(zip_saved):
            with open(zip_saved, "rb") as f:
                st.download_button(
                    "⬇️ Download all Shorts (ZIP)",
                    data=f.read(),
                    file_name="Ajay_AI_Creator_Shorts.zip",
                    mime="application/zip"
                )

elif page == "Shorts & Captions":
    st.title("✍️ Shorts & Captions")
    st.info("Caption editor is available as a draft. Automatic speech-to-text captions and AI titles/hashtags are not connected yet.")
    title = st.text_input("Shorts Title")
    caption = st.text_area("Write your caption")
    hashtags = st.text_input("Hashtags")
    if st.button("Save Draft"):
        st.session_state["ajay_draft"] = {"title": title, "caption": caption, "hashtags": hashtags}
        st.success("Draft saved in this session.")

elif page == "YouTube Channels":
    st.title("📺 YouTube Channels")
    st.warning("YouTube OAuth is not configured yet. No channel is connected and no video will be published.")
    st.write("The next stage needs Google Cloud project setup, YouTube Data API access and your explicit channel authorization.")

elif page == "Schedule":
    st.title("🗓️ Publishing Schedule")
    st.warning("Automatic YouTube scheduling is not active yet.")
    st.write("After secure channel authorization, we can add upload-and-schedule publishing.")

st.divider()
st.caption("Ajay AI Creator | Free Starter Version")
