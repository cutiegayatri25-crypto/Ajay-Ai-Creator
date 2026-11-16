# Ajay AI Creator

A free-first personal Shorts maker hosted on Streamlit Community Cloud.

## Available in the current free build
- Upload a video file (MP4, MOV, MKV, WEBM).
- Create vertical 9:16 clips with the complete original frame visible over a blurred background.
- Choose 1–10 clips and 15/30/45/60-second lengths.
- Download each generated MP4 separately.
- Paste a YouTube URL for best-effort downloading where YouTube permits it.
- Basic draft title, description and tags are shown for each Short.

## YouTube OAuth and scheduled upload setup
- The app now includes a Google OAuth connection flow and a YouTube upload/schedule form.
- These features remain inactive until the owner configures a Google Cloud OAuth Web Client and adds `[google_oauth]` secrets in Streamlit Community Cloud.
- Required Streamlit secrets: `client_id`, `client_secret`, and `redirect_uri` under `[google_oauth]`. Never commit these secrets to GitHub or share them in chat.
- Enable YouTube Data API v3, configure the exact app URL as an Authorized redirect URI, and add the Google account as a test user if the OAuth consent screen is in Testing.
- The app requests YouTube upload and read-only scopes. After connecting, a generated Short can be uploaded as Private with a future `publishAt` time (IST).
- OAuth credentials currently live only in the active Streamlit session. A persistent encrypted token store is still needed for reliable multi-session/multi-channel use; do not treat this as a finished multi-user production system.

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
