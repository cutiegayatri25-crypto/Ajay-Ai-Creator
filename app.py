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
.stApp { background: linear-gradient(135deg, #101026 0%, #17143b 55%, #0b2233 100%); color: #f4f7ff; }
h1, h2, h3 { color: #55e6df; }
[data-testid="stSidebar"] { background: #11132b; }
[data-testid="stMetric"] { background: rgba(41, 51, 91, 0.55); padding: 12px; border: 1px solid #38466d; border-radius: 12px; }
[data-testid="stAlert"] { border-radius: 12px; }
div.stButton > button {
    background: #e7b94f; color: #111827;
    border-radius: 8px; font-weight: bold;
    padding: 0.22rem 0.35rem; min-height: 1.9rem;
    font-size: 0.72rem; line-height: 1.0;
}
div[data-testid="stDownloadButton"] > button {
    padding: 0.20rem 0.28rem; min-height: 1.8rem;
    font-size: 0.68rem; line-height: 1.0;
    white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)

def show_logo(path, width):
    try:
        if Path(path).exists():
            st.image(path, width=width)
    except Exception:
        # Keep the app running if an optional logo file is invalid.
        pass

# Show the same profile logo once in the sidebar.
with st.sidebar:
    show_logo("logo.webp", 72)

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

def transcribe_video(source):
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(source), vad_filter=True, beam_size=1)
    rows = []
    for seg in segments:
        txt = (seg.text or "").strip()
        if txt:
            rows.append({"start": float(seg.start), "end": float(seg.end), "text": txt})
    if not rows:
        raise RuntimeError("No clear speech was detected.")
    return rows, info.language or "unknown"


def write_srt(rows, clip_start, clip_length, path):
    def stamp(value):
        ms = int(max(0, value) * 1000)
        hh, ms = divmod(ms, 3600000)
        mm, ms = divmod(ms, 60000)
        ss, ms = divmod(ms, 1000)
        return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"
    lines = []
    n = 1
    for seg in rows:
        left = max(clip_start, seg["start"])
        right = min(clip_start + clip_length, seg["end"])
        if right > left:
            lines += [str(n), f"{stamp(left-clip_start)} --> {stamp(right-clip_start)}", seg["text"], ""]
            n += 1
    Path(path).write_text("\\n".join(lines), encoding="utf-8")


def choose_starts(rows, total, clip_len, count):
    if total <= clip_len:
        return [0.0]
    hooks = ["why", "how", "secret", "truth", "never", "best", "mistake", "amazing",
             "কেন", "কিভাবে", "সত্যি", "গোপন", "ভুল", "কিন্তু", "কেন", "कैसे", "क्यों", "सच"]
    candidates = []
    step = max(3.0, min(8.0, clip_len / 4))
    t = 0.0
    while t <= total - clip_len:
        score = 0.0
        for seg in rows:
            overlap = max(0.0, min(t + clip_len, seg["end"]) - max(t, seg["start"]))
            if overlap:
                txt = seg["text"].lower()
                score += min(24, len(txt.split())) * 0.35 * overlap
                score += sum(1.5 for word in hooks if word in txt) * overlap
                score += (1.0 if "?" in txt or "!" in txt else 0.0) * overlap
        candidates.append((score, t))
        t += step
    candidates.sort(reverse=True)
    chosen = []
    for score, start in candidates:
        if all(abs(start - old) >= clip_len * 0.75 for old in chosen):
            chosen.append(start)
            if len(chosen) == count:
                break
    return sorted(chosen or [0.0])


def create_clips(source, output_dir, duration, count, progress, transcript):
    total = probe_duration(source)
    if total < 3:
        raise ValueError("This video is too short to create Shorts.")
    clip_len = min(float(duration), total)
    starts = choose_starts(transcript, total, clip_len, count)
    outputs, subtitles = [], []
    for index, start in enumerate(starts, 1):
        out = Path(output_dir) / f"Ajay_Short_{index:02d}.mp4"
        make_vertical_clip(source, out, start, clip_len)
        srt = Path(output_dir) / f"Ajay_Short_{index:02d}.srt"
        write_srt(transcript, start, clip_len, srt)
        outputs.append(out)
        subtitles.append(srt)
        progress.progress(int(index / len(starts) * 100), text=f"Creating Short {index} of {len(starts)}...")
    return outputs, subtitles, total

if page == "Dashboard":
    # One larger copy of the same logo in the main dashboard; no duplicate above it.
    show_logo("logo.webp", 210)
    st.title("🎬 Ajay AI Creator")
    st.subheader("Your Personal AI Shorts Studio")
    st.markdown("### 🔗 YouTube লিংক এখানে পেস্ট করুন")
    st.text_input("YouTube ভিডিওর লিংক", placeholder="https://www.youtube.com/watch?v=...", key="youtube_url_input")
    st.info("লিংক দেওয়ার পর বাম পাশের Upload Video পেজে যান এবং “YouTube লিংক থেকে Shorts তৈরি করুন” চাপুন।")
    st.success("Welcome to your AI Shorts Studio!")
    col1, col2, col3 = st.columns(3)
    col1.metric("Video tools", "Ready")
    col2.metric("Individual MP4 export", "Ready")
    col3.metric("YouTube channels", "Not connected")
    st.divider()
    st.header("Start Creating")
    st.write("Upload a video you own or have permission to process.")
    st.info("Stable framing, automatic speech-to-text subtitles and transcript-assisted highlight suggestions are included. Viral results are not guaranteed.")

elif page == "Upload Video":
    st.title("📤 Upload Video অথবা YouTube লিংক")
    st.caption("শুধু নিজের ভিডিও বা ব্যবহারের অনুমতি থাকা ভিডিও ব্যবহার করুন।")

    st.subheader("🔗 YouTube লিংক থেকে Shorts")
    youtube_url = st.text_input("YouTube ভিডিওর লিংক দিন", placeholder="https://www.youtube.com/watch?v=...", key="youtube_url_input")
    yt_count = st.slider("কতটি Shorts তৈরি করবেন?", 1, 10, 10, key="yt_count")
    yt_duration = st.selectbox("প্রতিটি Short কত সেকেন্ড?", [15, 30, 45, 60], index=1, key="yt_duration")
    st.caption("পাবলিক ও ডাউনলোড-অনুমোদিত ভিডিওতে কাজ করতে পারে। প্রাইভেট, সদস্য-শুধু, বয়স-সীমাবদ্ধ বা DRM-সুরক্ষিত ভিডিও নাও চলতে পারে।")
    if st.button("▶ YouTube লিংক থেকে Shorts তৈরি করুন", type="primary", disabled=not youtube_url.strip()):
        if not find_tool("ffmpeg") or not find_tool("ffprobe"):
            st.error("সার্ভারে FFmpeg ইনস্টল নেই।")
        else:
            yt_dir = tempfile.mkdtemp(prefix="ajay_youtube_")
            progress = st.progress(3, text="YouTube ভিডিওর তথ্য যাচাই হচ্ছে...")
            try:
                import yt_dlp
                opts = {
                    "format": "bestvideo*+bestaudio/best",
                    "format_sort": ["res:1080", "ext:mp4:m4a"],
                    "outtmpl": str(Path(yt_dir) / "source.%(ext)s"),
                    "merge_output_format": "mp4",
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "restrictfilenames": True,
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(youtube_url.strip(), download=True)
                    downloaded = Path(ydl.prepare_filename(info))
                if not downloaded.exists():
                    candidates = list(Path(yt_dir).glob("source.*"))
                    if not candidates:
                        raise RuntimeError("ভিডিও ফাইল ডাউনলোড সম্পূর্ণ হয়নি।")
                    downloaded = candidates[0]
                progress.progress(15, text="ভিডিও থেকে কথা শনাক্ত ও সাবটাইটেল তৈরি হচ্ছে...")
                transcript, language = transcribe_video(downloaded)
                out_dir = Path(yt_dir) / "shorts"
                out_dir.mkdir()
                outputs, subtitle_files, total = create_clips(
                    downloaded, out_dir, yt_duration, yt_count, progress, transcript
                )
                st.session_state["ajay_yt_short_files"] = [str(p) for p in outputs]
                st.session_state["ajay_yt_short_names"] = [p.name for p in outputs]
                st.session_state["ajay_yt_subtitle_files"] = [str(p) for p in subtitle_files]
                st.success(f"{info.get('title', 'ভিডিও')} থেকে {len(outputs)}টি Shorts তৈরি হয়েছে। ভাষা: {language}")
                st.info("প্রতিটি Short-এর জন্য আলাদা SRT সাবটাইটেল ফাইলও তৈরি হয়েছে।")
            except Exception as exc:
                st.error(f"YouTube লিংক থেকে ভিডিও তৈরি করা যায়নি: {exc}")
                st.caption("কিছু ভিডিও YouTube-এর সীমাবদ্ধতা, অনুমতি বা সার্ভার নীতির কারণে ডাউনলোড করা যায় না। সে ক্ষেত্রে নিজের অনুমোদিত ভিডিও ফাইলটি Upload Video অংশে আপলোড করুন।")

    yt_files = st.session_state.get("ajay_yt_short_files", [])
    yt_names = st.session_state.get("ajay_yt_short_names", [])
    yt_srts = st.session_state.get("ajay_yt_subtitle_files", [])
    if yt_files:
        st.subheader("YouTube থেকে তৈরি Shorts")
        for row_start in range(0, len(yt_files), 5):
            cols = st.columns(5, gap="small")
            for col, i in zip(cols, range(row_start, min(row_start + 5, len(yt_files)))):
                with col:
                    st.markdown(f"**Short {i + 1}**")
                    if os.path.exists(yt_files[i]):
                        st.video(yt_files[i])
                        with open(yt_files[i], "rb") as vf:
                            st.download_button("⬇ MP4", vf.read(), file_name=yt_names[i], mime="video/mp4", key=f"yt_mp4_{i}")
                    if i < len(yt_srts) and os.path.exists(yt_srts[i]):
                        with open(yt_srts[i], "rb") as sf:
                            st.download_button("💬 SRT", sf.read(), file_name=Path(yt_srts[i]).name, mime="application/x-subrip", key=f"yt_srt_{i}")

    st.divider()
    st.subheader("অথবা ভিডিও ফাইল আপলোড করুন")
    st.caption("বড় ভিডিও আপলোডে সার্ভারের মেমোরি ও সাইজের সীমা থাকতে পারে।")
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
        st.info("ভিডিওর কথা শুনে সাবটাইটেল তৈরি হবে এবং কথার আকর্ষণীয় অংশ দেখে ক্লিপ সাজেস্ট হবে।")
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
                    progress.progress(5, text="Transcribing speech for subtitles...")
                    transcript, language = transcribe_video(source_path)
                    outputs, subtitle_files, total = create_clips(
                        source_path, output_dir, clip_duration, clip_count, progress, transcript
                    )
                    st.session_state["ajay_short_files"] = [str(p) for p in outputs]
                    st.session_state["ajay_short_names"] = [p.name for p in outputs]
                    st.session_state["ajay_subtitle_files"] = [str(p) for p in subtitle_files]
                    st.success(f"Created {len(outputs)} suggested Shorts. Detected language: {language}.")
                    st.info("প্রতিটি ক্লিপের সাবটাইটেল .SRT ফাইল তৈরি হয়েছে। এটি সম্ভাবনাময় অংশের পরামর্শ, ভাইরাল হওয়ার নিশ্চয়তা নয়।")
                except Exception as exc:
                    st.error(f"Could not create Shorts: {exc}")

        saved_files = st.session_state.get("ajay_short_files", [])
        saved_names = st.session_state.get("ajay_short_names", [])
        saved_subtitles = st.session_state.get("ajay_subtitle_files", [])
        if saved_files:
            st.divider()
            st.subheader("Your Shorts")
            st.caption("ছোট প্রিভিউ দেখুন এবং প্রতিটি ভিডিও আলাদাভাবে MP4 হিসেবে ডাউনলোড করুন।")
            existing = [
                (idx, file_path, file_name)
                for idx, (file_path, file_name) in enumerate(zip(saved_files, saved_names), 1)
                if os.path.exists(file_path)
            ]
            # Six narrow cards per row with compact download controls.
            for row_start in range(0, len(existing), 6):
                card_columns = st.columns(6, gap="small")
                for column, item in zip(card_columns, existing[row_start:row_start + 6]):
                    idx, file_path, file_name = item
                    with column:
                        st.markdown(f"**Short {idx}**")
                        st.video(file_path)
                        with open(file_path, "rb") as f:
                            st.download_button(
                                "⬇ MP4",
                                data=f.read(),
                                file_name=file_name,
                                mime="video/mp4",
                                key=f"download_short_{idx}",
                                use_container_width=True
                            )
                        if len(saved_subtitles) >= idx and os.path.exists(saved_subtitles[idx - 1]):
                            with open(saved_subtitles[idx - 1], "rb") as sf:
                                st.download_button(
                                    "💬 SRT",
                                    data=sf.read(),
                                    file_name=Path(saved_subtitles[idx - 1]).name,
                                    mime="application/x-subrip",
                                    key=f"download_srt_{idx}",
                                    use_container_width=True
                                )

elif page == "Shorts & Captions":
    st.title("✍️ Shorts & Captions")
    st.info("Upload Video পেজে অটোমেটিক সাবটাইটেল তৈরি হবে। প্রতিটি Short-এর পাশে .SRT ডাউনলোড পাবেন।")
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
