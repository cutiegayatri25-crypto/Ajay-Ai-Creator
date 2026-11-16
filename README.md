# Ajay AI Creator

A free-first personal Shorts maker hosted on Streamlit Community Cloud.

## Available in the current free build
- Upload a video file (MP4, MOV, MKV, WEBM).
- Create vertical 9:16 clips with the complete original frame visible over a blurred background.
- Choose 1–10 clips and 15/30/45/60-second lengths.
- Download each generated MP4 separately.
- Paste a YouTube URL for best-effort downloading where YouTube permits it.
- Basic draft title, description and tags are shown for each Short.

## YouTube connection and scheduling status
- The current app does **not** contain a working Google OAuth connection flow or YouTube upload form.
- The YouTube Channels page only keeps channel URLs in the active Streamlit session. It does not authenticate a Google account.
- The Schedule page only keeps a temporary planning list in the active Streamlit session. It does not upload or schedule videos on YouTube.
- Real YouTube publishing requires a Google OAuth flow, YouTube Data API integration, secure secrets, and persistent token/storage handling. These are not implemented in this starter build.

## Temporarily unavailable / not yet connected
- Automatic speech-to-text captions: paused to keep the free cloud deployment lightweight.
- Transcript-based AI highlight detection: paused with speech recognition; clips are currently selected at evenly spaced points.
- Multiple channel accounts, invite-only user accounts and persistent user storage: not implemented yet; they require secure authentication and a persistent database.

## Important notes
- YouTube may block downloads from cloud-hosted IP addresses. Upload your own permitted video file if a URL download fails.
- Streamlit Community Cloud has resource and upload limits; very large videos may fail or run out of memory.
- The schedule page currently stores a draft in the active session only. It does not upload or schedule a video on YouTube.
- Use only videos you own or have permission to process.

This project is being developed in a free-first approach. Features that require paid services or private credentials are left disconnected rather than pretending they are working.
