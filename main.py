import os
import tkinter as tk
import asyncio
import threading
from pathlib import Path

import customtkinter as ctk

from modules.gui.app import TextToSpeechApp
from modules.utils.voice_manager import VoiceManager
from modules.conversion.converter import AudioConverter

def main():
    # Initialize managers
    voice_manager = VoiceManager()
    audio_converter = AudioConverter(voice_manager)
    
    # Create and run the application
    app = TextToSpeechApp(voice_manager, audio_converter)
    app.mainloop()

if __name__ == "__main__":
    main()