import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import os
import scipy.io.wavfile as wav
import soundfile as sf
from scipy.signal import butter, lfilter
from datetime import datetime
import json
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, WebRtcMode
import av
import io
from twilio.rest import Client

st.set_page_config(layout="wide")
st.title("💓 HEARTEST : Giri's PCG analyzer")

# Directories
UPLOAD_FOLDER = "uploaded_audios"
PATIENT_DATA = "patient_data.json"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load/save patient data
def save_patient_data(data):
    if os.path.exists(PATIENT_DATA):
        with open(PATIENT_DATA, "r") as f:
            existing = json.load(f)
    else:
        existing = []
    existing.append(data)
    with open(PATIENT_DATA, "w") as f:
        json.dump(existing, f)

def load_patient_data():
    if os.path.exists(PATIENT_DATA):
        with open(PATIENT_DATA, "r") as f:
            return json.load(f)
    return []

# SMS sender function using Twilio
def send_sms(phone_number, message):
    TWILIO_ACCOUNT_SID = "AC15ee7441c990e6e8a5afc996ed4a55a1"
    TWILIO_AUTH_TOKEN = "6bc0831dae8edb1753ace573a92b6337"
    TWILIO_PHONE_NUMBER = "+19096391894"

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=message,
        from_=TWILIO_PHONE_NUMBER,
        to=phone_number
    )

# Noise reduction
def reduce_noise(audio, sr, cutoff=0.05):
    b, a = butter(6, cutoff)
    return lfilter(b, a, audio)

# Audio analysis with editing controls
def display_waveform(path, label):
    sr, audio = wav.read(path)
    if audio.ndim > 1:
        audio = audio[:, 0]

    if st.button(f"🛠 Edit {label} Waveform"):
        with st.expander(f"🎛 Edit Parameters - {label}", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                amplitude_factor = st.slider(f"{label} Amplitude", 0.1, 5.0, 1.0, key=f"amp_{label}")
            with col2:
                duration_slider = st.slider(f"{label} Duration (s)", 1, int(len(audio) / sr), 5, key=f"dur_{label}")
            with col3:
                noise_cutoff = st.slider(f"{label} Noise Cutoff", 0.01, 0.5, 0.05, step=0.01, key=f"noise_{label}")

            zoom_start, zoom_end = st.slider(
                f"{label} Zoom (s)", 0.0, float(duration_slider), (0.0, float(duration_slider)), step=0.1, key=f"zoom_{label}"
            )

            adjusted_audio = audio[:duration_slider * sr] * amplitude_factor
            filtered_audio = reduce_noise(adjusted_audio, sr, cutoff=noise_cutoff)

            start_idx = int(zoom_start * sr)
            end_idx = int(zoom_end * sr)
            zoomed_audio = filtered_audio[start_idx:end_idx]

            fig, ax = plt.subplots()
            times = np.linspace(zoom_start, zoom_end, len(zoomed_audio))
            ax.plot(times, zoomed_audio)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            st.pyplot(fig)

            if st.checkbox(f"🔉 Play Denoised {label} Audio", key=f"denoise_{label}"):
                denoised_audio_io = io.BytesIO()
                wav.write(denoised_audio_io, sr, filtered_audio.astype(np.int16))
                st.audio(denoised_audio_io, format='audio/wav')

# Grid upload section
st.subheader("🎧 Upload Heart Valve Sounds")
valve_labels = ["Aortic", "Pulmonary", "Tricuspid", "Mitral"]
valve_paths = {}
cols = st.columns(4)

for i, label in enumerate(valve_labels):
    with cols[i]:
        file = st.file_uploader(f"Upload {label} Valve", type=["wav"], key=f"upload_{label}")
        if file:
            path = os.path.join(UPLOAD_FOLDER, f"{label}_{file.name}")
            with open(path, "wb") as f:
                f.write(file.getbuffer())
            st.audio(path, format="audio/wav")
            valve_paths[label] = path
            display_waveform(path, label)

# Sidebar: Upload and Recording
st.sidebar.header("📁 Upload or Record")
upload_file = st.sidebar.file_uploader("Upload WAV File", type=["wav"])

class AudioProcessor(AudioProcessorBase):
    def __init__(self):
        self.frames = []
    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        self.frames.append(frame)
        return frame

rec_path = None
ctx = webrtc_streamer(
    key="record",
    mode=WebRtcMode.SENDONLY,
    audio_receiver_size=1024,
    media_stream_constraints={"video": False, "audio": True},
    audio_processor_factory=AudioProcessor,
    async_processing=True,
)

if ctx.audio_receiver:
    if st.sidebar.button("🎙️ Save Microphone Recording"):
        audio_frames = ctx.audio_receiver.get_frames(timeout=1)
        if audio_frames:
            raw_audio = np.concatenate([frame.to_ndarray().flatten() for frame in audio_frames])
            raw_audio = (raw_audio * 32767).astype(np.int16)
            rec_path = os.path.join(UPLOAD_FOLDER, "recorded.wav")
            wav.write(rec_path, rate=48000, data=raw_audio)
            st.sidebar.success("Recording saved.")
        else:
            st.sidebar.warning("No audio captured.")

# Determine final audio path
path = None
if upload_file:
    path = os.path.join(UPLOAD_FOLDER, upload_file.name)
    with open(path, "wb") as f:
        f.write(upload_file.getbuffer())
    st.success("File uploaded successfully!")
    st.audio(path, format="audio/wav")
elif rec_path:
    path = rec_path
    st.audio(path, format="audio/wav")

# Patient Info Sidebar
if "patient_saved" not in st.session_state:
    st.session_state["patient_saved"] = False

with st.sidebar.expander("🧾 Add Patient Info"):
    name = st.text_input("Name")
    age = st.number_input("Age", 1, 120)
    gender = st.radio("Gender", ["Male", "Female", "Other"])
    notes = st.text_area("Clinical Notes")
    phone = st.text_input("📞 Patient Phone (E.g. +15558675309)")

    if st.button("💾 Save Patient Case"):
        if path:
            filename = os.path.basename(path)
            data = {
                "name": name,
                "age": age,
                "gender": gender,
                "notes": notes,
                "file": filename,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_patient_data(data)
            st.session_state["patient_saved"] = True
            st.success("Patient data saved. Now analyzing the audio...")
        else:
            st.warning("Please upload or record a PCG file before saving.")

    if st.button("📤 Send Case via SMS"):
        if path and phone:
            try:
                message = (
                    f"🩺 PCG Case Summary\n"
                    f"Name: {name}\nAge: {age}\nGender: {gender}\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nNotes: {notes}"
                )
                send_sms(phone, message)
                st.success("📨 Case sent via SMS.")
            except Exception as e:
                st.error(f"❌ Failed to send SMS: {e}")
        else:
            st.warning("Please enter a valid phone number and upload or record an audio.")

if path and st.session_state["patient_saved"]:
    display_waveform(path, "Final")

# Case History Section
st.subheader("📚 Case History")
patient_data = load_patient_data()
if patient_data:
    for i, entry in enumerate(patient_data[::-1]):
        with st.expander(f"📌 {entry['name']} ({entry['age']} y/o) - {entry['date']}"):
            st.write(f"**Gender:** {entry['gender']}")
            st.write(f"**Notes:** {entry['notes']}")
            file_path = os.path.join(UPLOAD_FOLDER, entry["file"])
            if os.path.exists(file_path):
                st.audio(file_path, format="audio/wav")
                display_waveform(file_path, f"history_{i}")
            else:
                st.error("Audio file missing.")
else:
    st.info("No history records found.")
    
