import librosa
import numpy as np
import os

audio_path = "C:/Users/jesuc/Downloads/Music/Gradio.wav"
if not os.path.exists(audio_path):
    print("Audio file does not exist at:", audio_path)
else:
    print("File exists, size:", os.path.getsize(audio_path), "bytes")
    try:
        y, sr = librosa.load(audio_path, sr=None)
        duration = len(y) / sr
        print(f"Sample rate: {sr} Hz")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Number of channels: {1 if len(y.shape) == 1 else y.shape[0]}")
        
        # Analyze first 10 seconds
        y_10s = y[:int(10 * sr)]
        rms_10s = np.sqrt(np.mean(y_10s**2))
        print(f"RMS amplitude of first 10s: {rms_10s:.5f}")
        
        # Check for silence (RMS < 0.001)
        if rms_10s < 0.001:
            print("WARNING: The first 10 seconds of the audio are almost silent!")
            
        # Print some values
        print("Max amplitude of first 10s:", np.max(np.abs(y_10s)))
    except Exception as e:
        print("Error reading audio:", e)
