
import streamlit as st

st.set_page_config(
    page_title="Ajay AI Creator",
    page_icon="🎬",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background: #0b1020;
    color: white;
}
h1, h2, h3 {
    color: #f4c95d;
}
[data-testid="stSidebar"] {
    background: #151f36;
}
div.stButton > button {
    background: #e7b94f;
    color: #111827;
    border-radius: 10px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🎬 Ajay AI Creator")
st.sidebar.caption("Your Personal AI Shorts Studio")

page = st.sidebar.radio(
    "MENU",
    [
        "Dashboard",
        "Upload Video",
        "Shorts & Captions",
        "YouTube Channels",
        "Schedule"
    ]
)

if page == "Dashboard":
    st.title("🎬 Ajay AI Creator")
    st.subheader("Your Personal AI Shorts Studio")

    st.success("Welcome to your AI Shorts Studio!")

    col1, col2, col3 = st.columns(3)

    col1.metric("Uploaded Videos", "0")
    col2.metric("Shorts Created", "0")
    col3.metric("YouTube Channels", "0")

    st.divider()

    st.header("Start Creating")
    st.write("Upload your video and prepare Shorts.")

elif page == "Upload Video":
    st.title("📤 Upload Your Video")

    video = st.file_uploader(
        "Choose a video",
        type=["mp4", "mov", "mkv", "webm"]
    )

    if video:
        st.video(video)
        st.success("Video selected successfully!")

    st.info("AI video processing will be added later.")

elif page == "Shorts & Captions":
    st.title("✍️ Shorts & Captions")

    title = st.text_input("Shorts Title")
    caption = st.text_area("Write your caption")
    hashtags = st.text_input("Hashtags")

    if st.button("Save Draft"):
        st.success("Draft saved for this session!")

elif page == "YouTube Channels":
    st.title("📺 YouTube Channels")
    st.info("YouTube account connection will be added later.")

elif page == "Schedule":
    st.title("🗓️ Publishing Schedule")
    st.info("Automatic YouTube scheduling will be added later.")

st.divider()
st.caption("Ajay AI Creator | Free Starter Version")
