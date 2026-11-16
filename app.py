import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

st.set_page_config(page_title="Ajay AI Creator", page_icon="logo.webp", layout="wide")

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

st.sidebar.image("logo.webp", width=76)
st.sidebar.title("Ajay AI Creator")
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

    # Add the app's own logo as a subtle watermark to every exported Short.
    logo_path = Path("logo.webp")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", temp_video, "-ss", str(start), "-i", str(source)
    ]
    if logo_path.exists():
        ffmpeg_cmd += [
            "-i", str(logo_path),
            "-filter_complex",
            "[2:v]scale=160:-1[logo];[0:v][logo]overlay=W-w-24:24:format=auto[v]",
            "-map", "[v]", "-map", "1:a:0?"
        ]
    else:
        ffmpeg_cmd += ["-map", "0:v:0", "-map", "1:a:0?"]
    ffmpeg_cmd += [
        "-t", str(length),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(output)
    ]
    mux = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    try:
        os.remove(temp_video)
    except OSError:
        pass
    if mux.returncode != 0:
        detail = mux.stderr[-1600:] if mux.stderr else "Audio/video export failed."
        raise RuntimeError(detail)
    return True

@st.cache_resource(show_spinner="Speech recognition model is loading for the first time...")
def load_whisper_model():
    # Optional feature: keep the core app deployable without the large ML runtime.
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    return WhisperModel("tiny", device="cpu", compute_type="int8")


def transcribe_video(source):
    model = load_whisper_model()
    if model is None:
        return [], "not enabled in free starter build"
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
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def burn_subtitles(video_path, srt_path):
    """Burn readable captions into the exported MP4; keep the SRT as a separate download too."""
    temp_out = str(video_path) + ".captioned.mp4"
    # Escape the filename for FFmpeg's subtitles filter on Linux.
    safe_srt = str(Path(srt_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{safe_srt}':force_style='FontSize=20,Outline=2,Shadow=1,Alignment=2,MarginV=48'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", "-movflags", "+faststart", temp_out
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and Path(temp_out).exists() and Path(temp_out).stat().st_size > 0:
        os.replace(temp_out, video_path)
    else:
        try:
            if Path(temp_out).exists():
                Path(temp_out).unlink()
        except OSError:
            pass
        # MP4 and downloadable SRT remain available even if the server lacks libass.

def choose_starts(rows, total, clip_len, count):
    if total <= clip_len:
        return [0.0]

    # Without the optional speech model, choose evenly spaced clips instead of
    # accidentally selecting the final moments of the source video.
    if not rows:
        max_unique = max(1, int((total - clip_len) / max(1.0, clip_len * 0.75)) + 1)
        actual_count = min(int(count), max_unique)
        if actual_count == 1:
            return [0.0]
        gap = (total - clip_len) / (actual_count - 1)
        return [round(i * gap, 2) for i in range(actual_count)]

    hooks = ["why", "how", "secret", "truth", "never", "best", "mistake", "amazing",
             "কেন", "কিভাবে", "সত্যি", "গোপন", "ভুল", "কিন্তু", "कैसे", "क्यों", "सच"]
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


def generate_metadata(rows, clip_start, clip_length, index=1):
    """Create a useful first-draft title, description and tags from the clip transcript."""
    import re
    text = " ".join(
        seg["text"] for seg in rows
        if seg["end"] > clip_start and seg["start"] < clip_start + clip_length
    ).strip()
    if not text:
        text = "একটি নতুন ভিডিও ক্লিপ"
    words = re.findall(r"[A-Za-z0-9অ-হা-য়ঁড়ঢ়য়ীুূৃেৈোৌংঃ]+", text.lower())
    stop = {
        "এই","এটা","সেটা","আমি","আমরা","আপনি","তুমি","এবং","কিন্তু","যে","কি","কেন","তো",
        "হয়","হবে","করতে","করে","একটা","আর","না","হ্যাঁ","এর","তার","থেকে","জন্য",
        "the","and","that","this","with","from","your","you","are","was","were","for",
        "have","has","had","but","not","what","when","where","how","why","then","just",
        "into","about","there","their","they","them","it's","its","can","will","would",
        "is","am","be","to","of","in","on","a","an","it"
    }
    counts = {}
    for w in words:
        if len(w) > 2 and w not in stop and not w.isdigit():
            counts[w] = counts.get(w, 0) + 1
    keywords = [w for w, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:6]]
    lead = " ".join(text.split()[:9]).strip(" ,.!?।")
    if len(lead) > 64:
        lead = lead[:61].rsplit(" ", 1)[0] + "…"
    title = f"{lead} | গুরুত্বপূর্ণ মুহূর্ত #{index}" if lead else f"এই ভিডিওর গুরুত্বপূর্ণ মুহূর্ত #{index}"
    tags = list(dict.fromkeys(["Shorts", "YouTubeShorts", "AjayAICreator"] + keywords))
    hashtags = " ".join("#" + re.sub(r"[^A-Za-z0-9_অ-হা-য়]", "", t) for t in tags[:8])
    description = (
        f"{text[:450]}{'…' if len(text) > 450 else ''}\n\n"
        f"আরও এমন ভিডিও দেখতে ফলো করুন।\n{hashtags}\n"
        "এই Short ভিডিওটির বক্তব্য থেকে স্বয়ংক্রিয়ভাবে তৈরি।"
    )
    return {"title": title[:100], "description": description, "tags": tags[:15], "transcript": text}


def save_clip_metadata(rows, starts, clip_length):
    return [generate_metadata(rows, start, clip_length, i) for i, start in enumerate(starts, 1)]


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
        burn_subtitles(out, srt)
        outputs.append(out)
        subtitles.append(srt)
        progress.progress(int(index / len(starts) * 100), text=f"Creating Short {index} of {len(starts)}...")
    return outputs, subtitles, total

if page == "Dashboard":
    # Use the actual uploaded app logo in place of the old video emoji icon.
    title_col_logo, title_col_text = st.columns([0.8, 8], vertical_alignment="center")
    with title_col_logo:
        show_logo("logo.webp", 76)
    with title_col_text:
        st.title("Ajay AI Creator")
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
    st.info("Stable vertical framing and MP4 export are included. Automatic speech-to-text captions are temporarily paused in this free starter build. Viral results are not guaranteed.")

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
                if not (youtube_url.strip().startswith("https://www.youtube.com/") or
                        youtube_url.strip().startswith("https://youtu.be/") or
                        youtube_url.strip().startswith("https://m.youtube.com/")):
                    raise ValueError("সঠিক YouTube ভিডিও লিংক দিন (youtube.com বা youtu.be)।")

                # Try a compatible combined format first, then fall back to best available.
                # YouTube may still block automated downloads or require account verification.
                base_opts = {
                    "outtmpl": str(Path(yt_dir) / "source.%(ext)s"),
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "retries": 3,
                    "fragment_retries": 3,
                    "extractor_retries": 2,
                    "socket_timeout": 25,
                    "file_access_retries": 2,
                    "restrictfilenames": True,
                    "cachedir": False,
                    "http_headers": {"User-Agent": "Mozilla/5.0"},
                    "source_address": "0.0.0.0",
                }
                last_error = None
                info = None
                downloaded = None
                for fmt in ("best", "best[ext=mp4]/best", "bestvideo*+bestaudio/best"):
                    try:
                        opts = dict(base_opts, format=fmt, merge_output_format="mp4")
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(youtube_url.strip(), download=True)
                            prepared = Path(ydl.prepare_filename(info))
                        candidates = [prepared] + list(Path(yt_dir).glob("source.*"))
                        downloaded = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
                        if downloaded:
                            break
                    except Exception as download_error:
                        last_error = download_error
                if not downloaded:
                    raise RuntimeError(
                        f"YouTube থেকে ভিডিও আনা যায়নি: {last_error or 'ডাউনলোড সম্পূর্ণ হয়নি'}. "
                        "YouTube-এর অস্থায়ী বাধা/লগইন/কপিরাইট সীমাবদ্ধতা থাকতে পারে। "
                        "নিজের ভিডিও হলে মূল MP4 ফাইল আপলোড করুন।"
                    )
                if not downloaded.exists():
                    candidates = list(Path(yt_dir).glob("source.*"))
                    if not candidates:
                        raise RuntimeError("ভিডিও ফাইল ডাউনলোড সম্পূর্ণ হয়নি।")
                    downloaded = candidates[0]
                progress.progress(15, text="ভিডিও প্রসেস করা হচ্ছে...")
                transcript, language = transcribe_video(downloaded)
                out_dir = Path(yt_dir) / "shorts"
                out_dir.mkdir()
                outputs, subtitle_files, total = create_clips(
                    downloaded, out_dir, yt_duration, yt_count, progress, transcript
                )
                st.session_state["ajay_yt_short_files"] = [str(p) for p in outputs]
                st.session_state["ajay_yt_short_names"] = [p.name for p in outputs]
                st.session_state["ajay_yt_subtitle_files"] = [str(p) for p in subtitle_files]
                clip_len = min(float(yt_duration), total)
                yt_starts = choose_starts(transcript, total, clip_len, len(outputs))
                st.session_state["ajay_yt_metadata"] = save_clip_metadata(transcript, yt_starts, clip_len)
                st.success(f"{info.get('title', 'ভিডিও')} থেকে {len(outputs)}টি Shorts তৈরি হয়েছে। ভাষা: {language}")
                st.info("ভিডিও প্রসেস সম্পন্ন। অটো ক্যাপশন সাময়িকভাবে বন্ধ; Shorts-এর সময় ভিডিও জুড়ে সমানভাবে বেছে নেওয়া হয়েছে।")
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
                    yt_meta = st.session_state.get("ajay_yt_metadata", [])
                    if i < len(yt_meta):
                        with st.expander("অটো Title / Description / Tags"):
                            st.write("**Title**")
                            st.write(yt_meta[i]["title"])
                            st.write("**Description**")
                            st.write(yt_meta[i]["description"])
                            st.write("**Tags**")
                            st.write(", ".join(yt_meta[i]["tags"]))
                    if os.path.exists(yt_files[i]):
                        st.video(yt_files[i])
                        with open(yt_files[i], "rb") as vf:
                            st.download_button("⬇ MP4", vf.read(), file_name=yt_names[i], mime="video/mp4", key=f"yt_mp4_{i}")
                    if i < len(yt_srts) and os.path.exists(yt_srts[i]) and os.path.getsize(yt_srts[i]) > 0:
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
        st.info("ভিডিও থেকে 9:16 Shorts তৈরি হবে। অটো ক্যাপশন সাময়িকভাবে বন্ধ; আপাতত ভিডিওর বিভিন্ন অংশ থেকে সমান ব্যবধানে ক্লিপ নেওয়া হবে।")
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
                    progress.progress(5, text="Preparing video clips...")
                    transcript, language = transcribe_video(source_path)
                    outputs, subtitle_files, total = create_clips(
                        source_path, output_dir, clip_duration, clip_count, progress, transcript
                    )
                    st.session_state["ajay_short_files"] = [str(p) for p in outputs]
                    st.session_state["ajay_short_names"] = [p.name for p in outputs]
                    st.session_state["ajay_subtitle_files"] = [str(p) for p in subtitle_files]
                    clip_len = min(float(clip_duration), total)
                    upload_starts = choose_starts(transcript, total, clip_len, len(outputs))
                    st.session_state["ajay_metadata"] = save_clip_metadata(transcript, upload_starts, clip_len)
                    st.success(f"Created {len(outputs)} suggested Shorts. Detected language: {language}.")
                    st.info("ভিডিও প্রসেস সম্পন্ন। এই ফ্রি স্টার্টার সংস্করণে অটো ক্যাপশন সাময়িকভাবে বন্ধ আছে।")
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
            # Four compact cards per row with compact download controls.
            for row_start in range(0, len(existing), 6):
                card_columns = st.columns(4, gap="small")
                for column, item in zip(card_columns, existing[row_start:row_start + 6]):
                    idx, file_path, file_name = item
                    with column:
                        st.markdown(f"**Short {idx}**")
                        upload_meta = st.session_state.get("ajay_metadata", [])
                        if idx <= len(upload_meta):
                            with st.expander("অটো Title / Description / Tags"):
                                st.write("**Title**")
                                st.write(upload_meta[idx - 1]["title"])
                                st.write("**Description**")
                                st.write(upload_meta[idx - 1]["description"])
                                st.write("**Tags**")
                                st.write(", ".join(upload_meta[idx - 1]["tags"]))
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
                        if len(saved_subtitles) >= idx and os.path.exists(saved_subtitles[idx - 1]) and os.path.getsize(saved_subtitles[idx - 1]) > 0:
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
    st.info("ভিডিও প্রসেস হলে প্রতিটি Short-এর জন্য প্রাথমিক Title, Description ও Tags সাজেশন দেখা যাবে। অটো সাবটাইটেল সাময়িকভাবে বন্ধ।")
    generated = st.session_state.get("ajay_metadata", []) or st.session_state.get("ajay_yt_metadata", [])
    if generated:
        for n, item in enumerate(generated, 1):
            with st.expander(f"Short {n} — তৈরি করা মেটাডেটা", expanded=(n == 1)):
                st.write("**Title**")
                st.code(item["title"])
                st.write("**Description**")
                st.text_area("Auto description", item["description"], key=f"meta_desc_{n}", height=110)
                st.write("**Tags**")
                st.write(", ".join(item["tags"]))
                st.caption("এগুলো প্রাথমিক ড্রাফট; বর্তমানে অটো ট্রান্সক্রিপ্ট/AI ক্যাপশন চালু নেই এবং ভাইরাল হওয়ার নিশ্চয়তা নয়।")
    else:
        st.warning("আগে Upload Video পেজে ভিডিও থেকে Shorts তৈরি করুন।")

elif page == "YouTube Channels":
    st.title("📺 YouTube Channels")
    st.warning("চ্যানেল কানেকশন এখনো চালু নয়। নিরাপদ YouTube OAuth অনুমোদন ছাড়া কোনো ভিডিও আপলোড বা প্রকাশ হবে না।")
    st.write("Google Cloud project, YouTube Data API এবং আপনার অনুমোদিত OAuth সংযোগ প্রয়োজন। পাসওয়ার্ড/OTP কখনো এখানে দেবেন না।")
    st.info("একাধিক নিজস্ব চ্যানেল আলাদা করে যুক্ত করার ব্যবস্থা পরের OAuth ধাপে সম্পূর্ণ হবে।")

elif page == "Schedule":
    st.title("🗓️ Shorts Timer & Schedule")
    st.info("এখানে শিডিউলের পরিকল্পনা তৈরি করা যাবে। YouTube-এ সত্যিকারের auto-publish চালু করতে আগে চ্যানেল OAuth সংযোগ লাগবে।")
    sched_date = st.date_input("প্রকাশের তারিখ")
    sched_time = st.time_input("প্রকাশের সময়")
    sched_channel = st.text_input("কোন নিজের চ্যানেলে প্রকাশ করবেন? (চ্যানেলের নাম)")
    sched_files = st.session_state.get("ajay_short_names", []) + st.session_state.get("ajay_yt_short_names", [])
    sched_video = st.selectbox("কোন Short শিডিউল করবেন?", sched_files) if sched_files else None
    if st.button("শিডিউল পরিকল্পনা সংরক্ষণ করুন", disabled=not (sched_channel.strip() and sched_video)):
        st.session_state.setdefault("ajay_schedule_drafts", []).append({
            "date": str(sched_date), "time": str(sched_time),
            "channel": sched_channel.strip(), "video": sched_video
        })
        st.success("শিডিউল পরিকল্পনা এই সেশনে সংরক্ষিত হয়েছে। এটি এখনো YouTube-এ আপলোড বা প্রকাশের সময় নির্ধারণ করেনি।")
    for entry in st.session_state.get("ajay_schedule_drafts", []):
        st.write(f"{entry['date']} {entry['time']} — {entry['channel']} — {entry['video']}")

st.divider()
st.caption("Ajay AI Creator | Free Starter Version")
