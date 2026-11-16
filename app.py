import os
import shutil
import subprocess
import tempfile
from pathlib import Path

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


@st.cache_resource
def ensure_bgutil_pot_provider():
    """Install and start a local PO-token provider once per Streamlit server process."""
    provider_dir = Path(tempfile.gettempdir()) / "bgutil-ytdlp-pot-provider-2.0.2"
    server_dir = provider_dir / "server"
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise RuntimeError("Node.js 22+ বা npm পাওয়া যায়নি; PO Token Provider চালু করা যায়নি।")
    if not (server_dir / "package.json").exists():
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", "2.0.2",
             "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git", str(provider_dir)],
            capture_output=True, text=True, timeout=180
        )
        if clone.returncode != 0:
            raise RuntimeError("PO Token Provider source download failed: " + (clone.stderr or clone.stdout)[-1200:])
    build_file = server_dir / "build" / "main.js"
    if not build_file.exists():
        install = subprocess.run(
            [npm, "ci"], cwd=str(server_dir), capture_output=True, text=True, timeout=300
        )
        if install.returncode != 0:
            raise RuntimeError("PO Token Provider dependency install failed: " + (install.stderr or install.stdout)[-1600:])
        compile_result = subprocess.run(
            [npm, "exec", "--", "tsc"], cwd=str(server_dir),
            capture_output=True, text=True, timeout=180
        )
        if compile_result.returncode != 0 or not build_file.exists():
            raise RuntimeError("PO Token Provider build failed: " + (compile_result.stderr or compile_result.stdout)[-1600:])
    existing = st.session_state.get("_bgutil_provider_process")
    if existing is not None and existing.poll() is None:
        return "http://127.0.0.1:4416"
    process = subprocess.Popen(
        [node, str(build_file), "--host", "127.0.0.1", "--port", "4416"],
        cwd=str(server_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    st.session_state["_bgutil_provider_process"] = process
    import time
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError("PO Token Provider server চালু হয়নি।")
    return "http://127.0.0.1:4416"


def save_dashboard_youtube_url():
    st.session_state["saved_youtube_url"] = st.session_state.get("youtube_url_dashboard", "").strip()


def save_upload_youtube_url():
    st.session_state["saved_youtube_url"] = st.session_state.get("youtube_url_upload", "").strip()

def probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip())

def make_vertical_clip(source, output, start, length, progress_callback=None):
    """Render a vertical clip in one FFmpeg pass for lower memory use and faster processing."""
    logo_path = Path("logo.webp")
    filters = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=720:1280:force_original_aspect_ratio=increase,"
        "crop=720:1280,boxblur=18:2,eq=brightness=-0.12[background];"
        "[fg]scale=720:1280:force_original_aspect_ratio=decrease[foreground];"
        "[background][foreground]overlay=(W-w)/2:(H-h)/2[base]"
    )
    cmd = ["ffmpeg", "-y", "-ss", str(max(0, start)), "-i", str(source)]
    video_map = "[base]"
    if logo_path.exists():
        filters += ";[1:v]scale=160:-1[logo];[base][logo]overlay=W-w-24:24:format=auto[v]"
        cmd += ["-i", str(logo_path)]
        video_map = "[v]"
    cmd += [
        "-t", str(length), "-filter_complex", filters,
        "-map", video_map, "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
        "-c:a", "aac", "-b:a", "128k", "-threads", "2",
        "-movflags", "+faststart", str(output)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not Path(output).exists() or Path(output).stat().st_size == 0:
        detail = result.stderr[-1400:] if result.stderr else "FFmpeg could not export this clip."
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
    transcript_text = text
    if not text:
        text = "এই Short-এর জন্য একটি প্রাথমিক খসড়া"
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
        ("ভিডিওর কথার ভিত্তিতে তৈরি প্রাথমিক খসড়া।" if transcript_text else
         "ভিডিওর ট্রান্সক্রিপ্ট পাওয়া যায়নি; প্রকাশের আগে নিজে Title ও Description যাচাই করুন.")
    )
    return {"title": title[:100], "description": description, "tags": tags[:15], "transcript": transcript_text}


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
    st.text_input(
        "YouTube ভিডিওর লিংক",
        value=st.session_state.get("saved_youtube_url", ""),
        placeholder="https://www.youtube.com/watch?v=...",
        key="youtube_url_dashboard",
        on_change=save_dashboard_youtube_url
    )
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
    youtube_url = st.text_input(
        "YouTube ভিডিওর লিংক দিন",
        value=st.session_state.get("saved_youtube_url", ""),
        placeholder="https://www.youtube.com/watch?v=...",
        key="youtube_url_upload",
        on_change=save_upload_youtube_url
    )
    yt_count = st.slider("কতটি Shorts তৈরি করবেন?", 1, 10, 3, key="yt_count")
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
                    "retries": 1,
                    "fragment_retries": 1,
                    "extractor_retries": 1,
                    "socket_timeout": 12,
                    "file_access_retries": 2,
                    "restrictfilenames": True,
                    "cachedir": False,
                    "http_headers": {"User-Agent": "Mozilla/5.0"},
                }
                def yt_download_progress(status):
                    if status.get("status") == "downloading":
                        total_bytes = status.get("total_bytes") or status.get("total_bytes_estimate")
                        if total_bytes:
                            pct = min(14, 3 + int(11 * status.get("downloaded_bytes", 0) / total_bytes))
                            progress.progress(pct, text=f"YouTube থেকে ভিডিও নামছে... {int(100 * status.get('downloaded_bytes', 0) / total_bytes)}%")
                        else:
                            progress.progress(5, text="YouTube থেকে ভিডিও নামছে...")
                    elif status.get("status") == "finished":
                        progress.progress(15, text="ভিডিও ডাউনলোড হয়েছে; এখন Shorts তৈরি হচ্ছে...")
                base_opts["progress_hooks"] = [yt_download_progress]
                info = None
                downloaded = None
                last_error = None
                # Start a local BgUtils PO-token provider before asking YouTube for formats.
                progress.progress(3, text="YouTube নিরাপদ ডাউনলোড সংযোগ প্রস্তুত হচ্ছে...")
                pot_provider_url = ensure_bgutil_pot_provider()
                # mweb uses the installed provider for video-server PO tokens.
                download_profiles = [
                    {"format": "best", "extractor_args": {"youtube": {"player_client": ["mweb"]}}},
                    {"format": "best", "extractor_args": {"youtube": {"player_client": ["web_safari"]}}},
                    {"format": "best", "extractor_args": {"youtube": {"player_client": ["android"]}}},
                ]
                for profile_index, profile in enumerate(download_profiles, 1):
                    try:
                        opts = dict(base_opts, merge_output_format="mp4", **profile)
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(youtube_url.strip(), download=True)
                            prepared = Path(ydl.prepare_filename(info))
                        candidates = [prepared] + list(Path(yt_dir).glob("source.*"))
                        downloaded = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
                        if downloaded:
                            break
                        last_error = "ডাউনলোডের পর ভিডিও ফাইল পাওয়া যায়নি।"
                    except Exception as download_error:
                        last_error = download_error
                        # Remove incomplete files before trying another YouTube client.
                        for partial in Path(yt_dir).glob("source.*"):
                            try:
                                partial.unlink()
                            except OSError:
                                pass
                        if profile_index < len(download_profiles):
                            progress.progress(8, text="এই পদ্ধতিতে ভিডিও পাওয়া যায়নি; বিকল্প YouTube পদ্ধতি চেষ্টা হচ্ছে...")
                if not downloaded:
                    raise RuntimeError(
                        f"YouTube ডাউনলোড ব্যর্থ হয়েছে: {last_error or 'ডাউনলোড সম্পূর্ণ হয়নি'}. "
                        "YouTube-এর সাম্প্রতিক ফরম্যাট/PO Token সীমাবদ্ধতার কারণে এই ভিডিওটি সার্ভার থেকে নামানো নাও যেতে পারে। "
                        "নিজের অনুমোদিত ভিডিও হলে MP4 ফাইল আপলোড করুন।"
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
                st.info("ভিডিও প্রসেস সম্পন্ন। এই Free Starter সংস্করণে অটো ট্রান্সক্রিপশন বন্ধ; তাই Shorts সমান ব্যবধানে তৈরি হয়েছে এবং Title/Description/Tags সাধারণ ড্রাফট হিসেবে দেখানো হবে।")
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
                        with st.expander("Title / Description / Tags"):
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
    st.caption("বড় ভিডিও আপলোডে ইন্টারনেটের গতি, Streamlit Cloud-এর আপলোড সীমা ও সার্ভারের মেমোরির কারণে সময় লাগতে পারে। প্রথমে 30–100 MB-এর ছোট MP4 দিয়ে পরীক্ষা করুন।")
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
        st.info("ভিডিও থেকে 9:16 Shorts তৈরি হবে। দ্রুত FFmpeg প্রসেসিং ব্যবহার করা হচ্ছে। অটো ক্যাপশন এই Free Starter সংস্করণে বন্ধ; ক্লিপগুলো সমান ব্যবধানে নেওয়া হবে।")
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
            for row_start in range(0, len(existing), 4):
                card_columns = st.columns(4, gap="small")
                for column, item in zip(card_columns, existing[row_start:row_start + 4]):
                    idx, file_path, file_name = item
                    with column:
                        st.markdown(f"**Short {idx}**")
                        upload_meta = st.session_state.get("ajay_metadata", [])
                        if idx <= len(upload_meta):
                            with st.expander("Title / Description / Tags"):
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
    st.write("এখানে তৈরি Shorts-এর Title, Description ও Tags দেখা ও সম্পাদনা করতে পারবেন।")
    file_meta = st.session_state.get("ajay_metadata", [])
    youtube_meta = st.session_state.get("ajay_yt_metadata", [])
    generated = [("আপলোড করা ভিডিও", file_meta), ("YouTube লিংক", youtube_meta)]
    shown = 0
    for source_label, items in generated:
        if items:
            st.subheader(source_label)
            for n, item in enumerate(items, 1):
                shown += 1
                with st.expander(f"{source_label} — Short {n}", expanded=(shown == 1)):
                    st.text_input("Title", value=item.get("title", ""), key=f"meta_{source_label}_{n}_title")
                    st.text_area("Description", value=item.get("description", ""), key=f"meta_{source_label}_{n}_description", height=110)
                    st.text_area("Tags (কমা দিয়ে আলাদা করুন)", value=", ".join(item.get("tags", [])), key=f"meta_{source_label}_{n}_tags", height=80)
                    if not item.get("transcript"):
                        st.info("এই Short-এর অডিও থেকে কথার ট্রান্সক্রিপ্ট তৈরি হয়নি। তাই Title/Description/Tags সাধারণ প্রাথমিক খসড়া; AI-তৈরি বা ভাইরাল বলে ধরে নেবেন না।")
    if not shown:
        st.warning("এখনো কোনো Short তৈরি হয়নি। বাম পাশের Upload Video পেজে গিয়ে ছোট MP4 আপলোড করে Create Shorts চাপুন।")
    st.divider()
    st.caption("অটো স্পিচ-টু-টেক্সট ক্যাপশন এই Free Starter সংস্করণে চালু নেই। SRT ফাইল তৈরি হলেও ট্রান্সক্রিপ্ট না থাকলে সেটি ফাঁকা থাকবে।")

elif page == "YouTube Channels":
    st.title("📺 YouTube Channels")
    st.caption("এখানে চ্যানেলের লিংক সংরক্ষণ করা যাবে। এটি Google OAuth সংযোগ নয়।")
    channels = st.session_state.setdefault("ajay_channel_links", [])
    with st.form("add_channel_form", clear_on_submit=True):
        channel_name = st.text_input("চ্যানেলের নাম (ঐচ্ছিক)")
        channel_url = st.text_input("YouTube Channel URL", placeholder="https://www.youtube.com/@yourchannel")
        submitted = st.form_submit_button("চ্যানেলের লিংক যোগ করুন")
    if submitted:
        url = channel_url.strip()
        if not (url.startswith("https://www.youtube.com/") or url.startswith("https://youtube.com/")):
            st.error("সঠিক YouTube channel URL দিন (https://www.youtube.com/...)।")
        elif any(c.get("url") == url for c in channels):
            st.warning("এই চ্যানেলের লিংকটি আগে থেকেই যোগ করা আছে।")
        elif len(channels) >= 5:
            st.warning("সর্বোচ্চ ৫টি চ্যানেল লিংক রাখা যাবে।")
        else:
            channels.append({"name": channel_name.strip() or "YouTube Channel", "url": url})
            st.success("চ্যানেলের লিংক এই সেশনে যোগ হয়েছে।")
    if channels:
        st.subheader("সংরক্ষিত চ্যানেল লিংক")
        for i, channel in enumerate(channels):
            left, right = st.columns([5, 1])
            left.markdown(f"**{channel['name']}**  \n{channel['url']}")
            if right.button("বাদ দিন", key=f"remove_channel_{i}"):
                channels.pop(i)
                st.rerun()
    st.warning("Google OAuth credentials এবং অনুমোদিত YouTube API সংযোগ এখনো সেট করা নেই। তাই এই লিংকগুলো দিয়ে ভিডিও আপলোড বা প্রকাশ করা যাবে না।")

elif page == "Schedule":
    st.title("🗓️ Schedule")
    st.write("এটি আপাতত আপনার প্রকাশের পরিকল্পনার তালিকা—এখান থেকে YouTube-এ ভিডিও আপলোড বা Auto Publish হয় না।")
    schedule_items = st.session_state.setdefault("ajay_schedule_items", [])
    available_shorts = st.session_state.get("ajay_short_names", []) + st.session_state.get("ajay_yt_short_names", [])
    with st.form("schedule_form", clear_on_submit=True):
        if available_shorts:
            selected_short = st.selectbox("কোন Short-এর জন্য পরিকল্পনা করবেন?", available_shorts)
        else:
            selected_short = st.text_input("Short-এর নাম লিখুন", placeholder="যেমন: Ajay_Short_01.mp4")
            st.caption("Short তৈরি না করেও পরিকল্পনার নাম লিখতে পারবেন।")
        schedule_date = st.date_input("প্রকাশের তারিখ")
        schedule_time = st.time_input("প্রকাশের সময়")
        channel_options = ["চ্যানেল নির্বাচন করা হয়নি"] + [
            c.get("name", c.get("url", "Channel")) for c in st.session_state.get("ajay_channel_links", [])
        ]
        selected_channel = st.selectbox("কোন চ্যানেলের জন্য?", channel_options)
        schedule_submitted = st.form_submit_button("পরিকল্পনা সংরক্ষণ করুন")
    if schedule_submitted:
        if not str(selected_short).strip():
            st.error("আগে তৈরি Short বেছে নিন অথবা Short-এর নাম লিখুন।")
        else:
            schedule_items.append({"short": str(selected_short).strip(), "date": str(schedule_date), "time": str(schedule_time), "channel": selected_channel})
            st.success("পরিকল্পনাটি এই সেশনে সংরক্ষিত হয়েছে।")
    if schedule_items:
        st.subheader("সংরক্ষিত পরিকল্পনা")
        for i, item in enumerate(schedule_items):
            st.write(f"{i+1}. {item['short']} — {item['date']} {item['time']} — {item['channel']}")
            if st.button("এই পরিকল্পনা মুছুন", key=f"delete_schedule_{i}"):
                schedule_items.pop(i)
                st.rerun()
    st.warning("গুরুত্বপূর্ণ: পরিকল্পনাগুলো শুধু Streamlit-এর বর্তমান session-এ থাকে; অ্যাপ restart হলে মুছে যেতে পারে। স্থায়ী সংরক্ষণ ও YouTube-এ নির্দিষ্ট সময়ে প্রকাশের জন্য database, Google OAuth এবং YouTube Data API কনফিগার করতে হবে।")

st.divider()
st.caption("Ajay AI Creator | Free Starter Version")
