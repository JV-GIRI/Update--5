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

    with st.expander(f"🎭 Edit Parameters - {label}", expanded=True):
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

        st.audio(io.BytesIO(wav_to_bytes(filtered_audio, sr)), format='audio/wav')

# Convert audio array to BytesIO WAV
def wav_to_bytes(audio_data, sample_rate):
    output = io.BytesIO()
    wav.write(output, sample_rate, audio_data.astype(np.int16))
    return output.getvalue()

# Upload section with styled buttons
st.subheader("🎧 Upload Heart Valve Sounds")
valve_labels = ["Aortic", "Pulmonary", "Tricuspid", "Mitral"]
valve_paths = {}
cols = st.columns(4)

for i, label in enumerate(valve_labels):
    with cols[i]:
        upload_style = """
        <style>
        .orange-upload > label div.stButton > button {
            background-color: orange !important;
            color: white !important;
        }
        </style>
        """
        st.markdown(upload_style, unsafe_allow_html=True)
        with st.container():
            file = st.file_uploader(f"Upload {label} Valve", type=["wav"], key=f"upload_{label}")
            if file:
                path = os.path.join(UPLOAD_FOLDER, f"{label}_{file.name}")
                with open(path, "wb") as f:
                    f.write(file.getbuffer())
                st.audio(path, format="audio/wav")
                valve_paths[label] = path
                display_waveform(path, label)

# Patient Info Sidebar (no upload option here now)
if "patient_saved" not in st.session_state:
    st.session_state["patient_saved"] = False

with st.sidebar.expander("🧾 Add Patient Info"):
    name = st.text_input("Name")
    age = st.number_input("Age", 1, 120)
    gender = st.radio("Gender", ["Male", "Female", "Other"])
    notes = st.text_area("Clinical Notes")
    phone = st.text_input("📞 Patient Phone (E.g. +15558675309)")

    if st.button("📂 Save Patient Case", type="primary"):
        if len(valve_paths) == 4:
            data = {
                "name": name,
                "age": age,
                "gender": gender,
                "notes": notes,
                "file": ", ".join([os.path.basename(valve_paths[k]) for k in valve_labels]),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_patient_data(data)
            st.session_state["patient_saved"] = True
            st.success("Patient data saved.")
        else:
            st.warning("Please upload all 4 valve audios.")

    if st.button("📤 Send Case via SMS"):
        if len(valve_paths) == 4 and phone:
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
            st.warning("Please complete all uploads and phone number.")

# Case History Section
st.subheader("📚 Case History")
patient_data = load_patient_data()
if patient_data:
    for i, entry in enumerate(patient_data[::-1]):
        with st.expander(f"📌 {entry['name']} ({entry['age']} y/o) - {entry['date']}"):
            st.write(f"**Gender:** {entry['gender']}")
            st.write(f"**Notes:** {entry['notes']}")
            for label in valve_labels:
                audio_file = os.path.join(UPLOAD_FOLDER, f"{label}_{entry['file'].split(', ')[0]}")
                if os.path.exists(audio_file):
                    st.audio(audio_file, format="audio/wav")
                    display_waveform(audio_file, f"history_{label}_{i}")
else:
    st.info("No history records found.")

# Add button styling
button_style = """
<style>
    div.stButton > button:first-child {
        background-color: #006400;
        color: white;
    }
</style>
"""
st.markdown(button_style, unsafe_allow_html=True)
            
