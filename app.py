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
[data-testid="stAppViewContainer"] .main .block-container { max-width: 1180px; padding-top: 2rem; }
.stApp [data-testid="stVerticalBlock"] > div:has(> [data-testid="stMetric"]) { gap: 0.8rem; }
.ajay-hero { padding: 28px 30px; border: 1px solid rgba(85,230,223,.28); border-radius: 20px; background: linear-gradient(120deg, rgba(31,42,83,.96), rgba(15,75,83,.72)); margin: 8px 0 22px; }
.ajay-hero h1 { font-size: 2.35rem; margin: 0 0 8px; color: #f5fbff; }
.ajay-hero p { color: #d5e8f3; font-size: 1.05rem; margin: 0; }
.ajay-feature { background: rgba(41,51,91,.42); border: 1px solid #38466d; border-radius: 14px; padding: 16px; min-height: 132px; }
.ajay-feature h3 { margin-top: 0; font-size: 1.05rem; }
.ajay-feature p { color: #d5d9e8; font-size: .9rem; }
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
        raise RuntimeError("Node.js 22+ or npm was not found; the PO Token Provider could not be started.")
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
    process = subprocess.Popen(
        [node, str(build_file), "--host", "127.0.0.1", "--port", "4416"],
        cwd=str(server_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    import time
    import urllib.request
    # Wait for the local provider's documented health endpoint instead of
    # assuming that a fixed sleep means the HTTP server is ready.
    health_error = None
    for _ in range(20):
        if process.poll() is not None:
            raise RuntimeError("The PO Token Provider process has stopped.")
        try:
            with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=2) as response:
                if response.status == 200:
                    return process
        except Exception as exc:
            health_error = exc
        time.sleep(0.5)
    process.terminate()
    raise RuntimeError(
        "PO Token Provider /ping health check failed: "
        + str(health_error or "no server response was received")
    )


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


def download_from_tunelio(youtube_url, api_key, output_path, progress):
    """Download an authorized YouTube video through the optional hosted Tunelio API."""
    import json
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode({"url": youtube_url, "quality": "720p"})
    request = urllib.request.Request(
        "https://tunelio.dev/create?" + query,
        headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
    )
    progress.progress(5, text="Requesting a download link from the alternative video service...")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "ok" or not payload.get("url"):
        raise RuntimeError(payload.get("error") or payload.get("message") or "The video download link was not available.")
    progress.progress(10, text="Downloading video...")
    media_request = urllib.request.Request(payload["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(media_request, timeout=180) as media_response, open(output_path, "wb") as output:
        shutil.copyfileobj(media_response, output)
    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise RuntimeError("The downloaded video file is empty.")
    progress.progress(15, text="Video downloaded; creating Shorts...")
    return {"title": payload.get("filename", "YouTube video")}, Path(output_path)

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
        text = "A draft for this Short"
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
    title = f"{lead} | Key Moment #{index}" if lead else f"এই ভিডিওর Key Moment #{index}"
    tags = list(dict.fromkeys(["Shorts", "YouTubeShorts", "AjayAICreator"] + keywords))
    hashtags = " ".join("#" + re.sub(r"[^A-Za-z0-9_অ-হা-য়]", "", t) for t in tags[:8])
    description = (
        f"{text[:450]}{'…' if len(text) > 450 else ''}\n\n"
        f"Follow for more videos like this.\n{hashtags}\n"
        ("Draft generated from the video's transcript." if transcript_text else
         "No transcript was available. Review the title and description before publishing.")
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
    st.markdown("""
    <section class="ajay-hero">
      <h1>🎬 Ajay AI Creator</h1>
      <p>লম্বা YouTube From video Key Moment বেছে Shorts তৈরি করুন।</p>
    </section>
    """, unsafe_allow_html=True)
    st.markdown("### 🚀 Paste Your Video Link")
    st.text_input(
        "YouTube Video URL",
        value=st.session_state.get("saved_youtube_url", ""),
        placeholder="https://www.youtube.com/watch?v=...",
        key="youtube_url_dashboard",
        on_change=save_dashboard_youtube_url
    )
    st.info("After adding the link, open Upload Video from the sidebar. Choose the number and length of your Shorts to get started.")
    col1, col2, col3 = st.columns(3)
    col1.metric("From One Video", "Up to 10", "Shorts")
    col2.metric("ভিডিও ফরম্যাট", "9:16", "Vertical")
    col3.metric("Cost", "Free Starter", "No credits required")
    st.divider()
    st.subheader("✨ Your Shorts Studio")
    feature_cols = st.columns(3)
    feature_cards = [
        ("🎯 Key Moment", "Find potentially engaging sections using transcript density, questions, and hook phrases when transcription is available."),
        ("📱 Vertical Shorts", "Convert long videos into vertical 9:16 MP4 clips."),
        ("✍️ Title ও Tags", "Editable title, description, and tag drafts for every clip."),
        ("💬 Subtitles", "Generate SRT captions and burn them into the video when transcription is enabled."),
        ("⬇️ Individual Downloads", "Download each Short as a separate MP4 file."),
        ("📺 YouTube Channel Integration", "Direct publishing and scheduling can be added after YouTube OAuth and API setup.")
    ]
    for i, (heading, detail) in enumerate(feature_cards):
        with feature_cols[i % 3]:
            st.markdown(f'<div class="ajay-feature"><h3>{heading}</h3><p>{detail}</p></div>', unsafe_allow_html=True)
    st.divider()
    st.caption("Note: AI-selected moments are not guaranteed to go viral. YouTube link processing depends on YouTube access and server restrictions. Use videos you own or have permission to process.")

elif page == "Upload Video":
    st.title("📤 Upload a Video or Paste a YouTube Link")
    st.caption("Only use videos you own or have permission to process.")

    st.subheader("🔗 Create Shorts from a YouTube Link")
    youtube_url = st.text_input(
        "YouTube Video URL দিন",
        value=st.session_state.get("saved_youtube_url", ""),
        placeholder="https://www.youtube.com/watch?v=...",
        key="youtube_url_upload",
        on_change=save_upload_youtube_url
    )
    tunelio_api_key = st.text_input(
        "Alternative Download Service API Key (Optional)",
        type="password",
        key="tunelio_api_key",
        help="Enter your own Tunelio API key. It is used for this Streamlit session and is not stored in the source code."
    )
    yt_count = st.slider("How many Shorts would you like to create?", 1, 10, 10, key="yt_count")
    yt_duration = st.selectbox("Length of each Short", [15, 30, 45, 60], index=1, key="yt_duration")
    st.caption("Works only with publicly accessible videos you are authorized to process. Private, members-only, age-restricted, or DRM-protected videos may not work.")
    if st.button("▶ Create Shorts from YouTube Link", type="primary", disabled=not youtube_url.strip()):
        if not find_tool("ffmpeg") or not find_tool("ffprobe"):
            st.error("FFmpeg is not installed on the server.")
        else:
            yt_dir = tempfile.mkdtemp(prefix="ajay_youtube_")
            progress = st.progress(3, text="Checking YouTube video information...")
            try:
                import yt_dlp
                if not (youtube_url.strip().startswith("https://www.youtube.com/") or
                        youtube_url.strip().startswith("https://youtu.be/") or
                        youtube_url.strip().startswith("https://m.youtube.com/")):
                    raise ValueError("Enter a valid YouTube video URL (youtube.com or youtu.be).")

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
                            progress.progress(pct, text=f"Downloading video from YouTube... {int(100 * status.get('downloaded_bytes', 0) / total_bytes)}%")
                        else:
                            progress.progress(5, text="Downloading video from YouTube...")
                    elif status.get("status") == "finished":
                        progress.progress(15, text="Video downloaded; creating Shorts...")
                base_opts["progress_hooks"] = [yt_download_progress]
                info = None
                downloaded = None
                last_error = None
                if tunelio_api_key.strip():
                    downloaded_path = Path(yt_dir) / "source.mp4"
                    try:
                        info, downloaded = download_from_tunelio(
                            youtube_url.strip(), tunelio_api_key.strip(), downloaded_path, progress
                        )
                    except Exception as api_error:
                        raise RuntimeError(
                            "The alternative download service failed. Check the API key, available credits, and video permissions. "
                            + str(api_error)
                        ) from api_error
                if not downloaded:
                    # Start the optional local BgUtils PO-token provider. If Node.js,
                    # npm, or provider setup is unavailable, still try yt-dlp's other
                    # download clients instead of aborting the entire YouTube workflow.
                    progress.progress(3, text="Preparing the YouTube download connection...")
                    pot_provider_process = None
                    try:
                        pot_provider_process = ensure_bgutil_pot_provider()
                    except Exception as provider_error:
                        st.warning(
                            "The PO Token Provider could not start; another YouTube download method will be attempted. "
                            + str(provider_error)
                        )
                    # mweb uses the installed provider for video-server PO tokens.
                    download_profiles = [
                        # BgUtils recommends trying these clients together so yt-dlp
                        # can request a PO token for a compatible client when needed.
                        {"format": "best", "extractor_args": {"youtube": {"player_client": ["mweb", "tv", "web_safari"]}}},
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
                            last_error = "The video file was not found after download."
                        except Exception as download_error:
                            last_error = download_error
                            # Remove incomplete files before trying another YouTube client.
                            for partial in Path(yt_dir).glob("source.*"):
                                try:
                                    partial.unlink()
                                except OSError:
                                    pass
                            if profile_index < len(download_profiles):
                                progress.progress(8, text="This method did not return a video; trying an alternative YouTube method...")
                if not downloaded:
                    error_text = str(last_error or "The download did not complete")
                    if "Sign in to confirm" in error_text or "not a bot" in error_text.lower():
                        raise RuntimeError(
                            "YouTube blocked this cloud server connection with a bot check. "
                            "Even with a PO Token Provider, YouTube does not allow every server or IP address. "
                            "If this is your video or you have permission to use it, upload an authorized MP4 file in the section below. "
                            "This is not an issue with your video; it is a server-side YouTube restriction. "
                            "Original error: " + error_text
                        )
                    raise RuntimeError(
                        f"YouTube download failed: {error_text}. "
                        "The video could not be downloaded because of YouTube format, PO Token, or network restrictions. "
                        "If you are authorized to use the video, upload an MP4 file instead."
                    )
                if not downloaded.exists():
                    candidates = list(Path(yt_dir).glob("source.*"))
                    if not candidates:
                        raise RuntimeError("ভিডিও ফাইল The download did not complete।")
                    downloaded = candidates[0]
                progress.progress(15, text="Processing video...")
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
                st.success(f"{info.get('title', 'ভিডিও')} থেকে {len(outputs)}Shorts created. Language: {language}")
                st.info("Video processing is complete. Automatic transcription is disabled in this Free Starter version, so clips were selected at even intervals and metadata is shown as a basic draft.")
            except Exception as exc:
                st.error(f"Could not create Shorts from the YouTube link: {exc}")
                st.caption("This link could not be processed because of YouTube server, PO Token, or network restrictions. Review the error details above.")

    yt_files = st.session_state.get("ajay_yt_short_files", [])
    yt_names = st.session_state.get("ajay_yt_short_names", [])
    yt_srts = st.session_state.get("ajay_yt_subtitle_files", [])
    if yt_files:
        st.subheader("Shorts Created from YouTube")
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
    st.subheader("Or Upload a Video File")
    st.caption("Large uploads may take time due to internet speed, Streamlit Cloud upload limits, and server memory. For testing, start with a small 30–100 MB MP4.")
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
        clip_count = st.slider("Number of Shorts", min_value=1, max_value=10, value=10)
        st.caption("The original video frame will be fitted without face tracking or dynamic reframing. The source aspect ratio will be preserved.")
        st.info("From video 9:16 Shorts তৈরি হবে। দ্রুত FFmpeg প্রসেসিং ব্যবহার করা হচ্ছে। অটো ক্যাপশন এই Free Starter সংস্করণে বন্ধ; ক্লিপগুলো সমান ব্যবধানে নেওয়া হবে।")
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
                    st.info("ভিডিও প্রসেস সম্পন্ন। এই Free Starter সংস্করণে অটো ক্যাপশন সাময়িকভাবে বন্ধ আছে।")
                except Exception as exc:
                    st.error(f"Could not create Shorts: {exc}")

        saved_files = st.session_state.get("ajay_short_files", [])
        saved_names = st.session_state.get("ajay_short_names", [])
        saved_subtitles = st.session_state.get("ajay_subtitle_files", [])
        if saved_files:
            st.divider()
            st.subheader("Your Shorts")
            st.caption("Preview your clips and download each video separately as an MP4.")
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
    st.write("View and edit titles, descriptions, and tags for your generated Shorts here.")
    file_meta = st.session_state.get("ajay_metadata", [])
    youtube_meta = st.session_state.get("ajay_yt_metadata", [])
    generated = [("Uploaded Video", file_meta), ("YouTube Link", youtube_meta)]
    shown = 0
    for source_label, items in generated:
        if items:
            st.subheader(source_label)
            for n, item in enumerate(items, 1):
                shown += 1
                with st.expander(f"{source_label} — Short {n}", expanded=(shown == 1)):
                    st.text_input("Title", value=item.get("title", ""), key=f"meta_{source_label}_{n}_title")
                    st.text_area("Description", value=item.get("description", ""), key=f"meta_{source_label}_{n}_description", height=110)
                    st.text_area("Tags (separate with commas)", value=", ".join(item.get("tags", [])), key=f"meta_{source_label}_{n}_tags", height=80)
                    if not item.get("transcript"):
                        st.info("No speech transcript was generated for this Short. The title, description, and tags are basic drafts—not AI-verified or guaranteed to go viral.")
    if not shown:
        st.warning("No Shorts have been created yet. Open Upload Video in the sidebar, upload a small MP4, and click Create Shorts.")
    st.divider()
    st.caption("Automatic speech-to-text captions are not enabled in this Free Starter version. An SRT file may be empty if no transcript is available.")

elif page == "YouTube Channels":
    st.title("📺 YouTube Channels")
    st.caption("You can save channel links here. This does not connect your account through Google OAuth.")
    channels = st.session_state.setdefault("ajay_channel_links", [])
    with st.form("add_channel_form", clear_on_submit=True):
        channel_name = st.text_input("Channel Name (Optional)")
        channel_url = st.text_input("YouTube Channel URL", placeholder="https://www.youtube.com/@yourchannel")
        submitted = st.form_submit_button("Add Channel Link")
    if submitted:
        url = channel_url.strip()
        if not (url.startswith("https://www.youtube.com/") or url.startswith("https://youtube.com/")):
            st.error("Enter a valid YouTube channel URL (https://www.youtube.com/...).")
        elif any(c.get("url") == url for c in channels):
            st.warning("This channel link has already been added.")
        elif len(channels) >= 5:
            st.warning("You can save up to 5 channel links.")
        else:
            channels.append({"name": channel_name.strip() or "YouTube Channel", "url": url})
            st.success("Channel link added to this session.")
    if channels:
        st.subheader("Saved Channel Links")
        for i, channel in enumerate(channels):
            left, right = st.columns([5, 1])
            left.markdown(f"**{channel['name']}**  \n{channel['url']}")
            if right.button("Remove", key=f"remove_channel_{i}"):
                channels.pop(i)
                st.rerun()
    st.warning("Google OAuth credentials and an authorized YouTube API connection are not configured yet. These links cannot be used to upload or publish videos.")

elif page == "Schedule":
    st.title("🗓️ Schedule")
    st.write("This is currently a publishing plan only. It does not upload or auto-publish videos to YouTube.")
    schedule_items = st.session_state.setdefault("ajay_schedule_items", [])
    available_shorts = st.session_state.get("ajay_short_names", []) + st.session_state.get("ajay_yt_short_names", [])
    with st.form("schedule_form", clear_on_submit=True):
        if available_shorts:
            selected_short = st.selectbox("Which Short would you like to schedule?", available_shorts)
        else:
            selected_short = st.text_input("Enter a Short name", placeholder="Example: Ajay_Short_01.mp4")
            st.caption("You can enter a plan even before creating a Short.")
        schedule_date = st.date_input("Publish Date")
        schedule_time = st.time_input("Publish Time")
        channel_options = ["No channel selected"] + [
            c.get("name", c.get("url", "Channel")) for c in st.session_state.get("ajay_channel_links", [])
        ]
        selected_channel = st.selectbox("Which channel?", channel_options)
        schedule_submitted = st.form_submit_button("Save Schedule")
    if schedule_submitted:
        if not str(selected_short).strip():
            st.error("আগে তৈরি Short বেছে নিন অথবা Enter a Short name।")
        else:
            schedule_items.append({"short": str(selected_short).strip(), "date": str(schedule_date), "time": str(schedule_time), "channel": selected_channel})
            st.success("Schedule saved for this session.")
    if schedule_items:
        st.subheader("Saved Schedules")
        for i, item in enumerate(schedule_items):
            st.write(f"{i+1}. {item['short']} — {item['date']} {item['time']} — {item['channel']}")
            if st.button("Delete this schedule", key=f"delete_schedule_{i}"):
                schedule_items.pop(i)
                st.rerun()
    st.warning("Important: Schedules are stored only in the current Streamlit session and may disappear when the app restarts. Persistent storage and scheduled YouTube publishing require a database, Google OAuth, and the YouTube Data API.")

st.divider()
st.caption("Ajay AI Creator | Free Starter Version")
