import os
import tkinter as tk
import asyncio
import threading
from pathlib import Path

import customtkinter as ctk

from modules.gui.app import TextToSpeechApp
from modules.utils.voice_manager import VoiceManager
from modules.utils.piper_manager import PiperVoiceManager
from modules.conversion.converter import AudioConverter

def main():
    # Initialize managers
    voice_manager = VoiceManager()
    piper_manager = PiperVoiceManager()
    audio_converter = AudioConverter(voice_manager, piper_manager)
    
    # Create and run the application
    app = TextToSpeechApp(voice_manager, audio_converter, piper_manager)
    app.mainloop()

if __name__ == "__main__":
    main()