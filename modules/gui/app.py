import os
import tkinter as tk
from tkinter import filedialog, messagebox
import asyncio
import threading
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import customtkinter as ctk

from modules.utils.voice_manager import VoiceManager
from modules.conversion.converter import AudioConverter
from modules.extractors import get_extractor

class TextToSpeechApp(ctk.CTk):
    def __init__(self, voice_manager: VoiceManager, audio_converter: AudioConverter):
        super().__init__()
        
        self.voice_manager = voice_manager
        self.audio_converter = audio_converter
        
        self.title("Conversor de Libros a Audio")
        self.geometry("800x600")
        ctk.set_appearance_mode("dark")
        
        self.input_file = ""
        self.output_file = ""
        self.is_processing = False
        self.conversion_thread: Optional[threading.Thread] = None
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.setup_ui()
        self.load_voices_async()
    
    def setup_ui(self):
        # Main frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(1, weight=1)
        
        # Title
        title_label = ctk.CTkLabel(
            self.main_frame, 
            text="Conversor de Libros a Audio",
            font=("Arial", 24, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=20)
        
        # File selection
        file_label = ctk.CTkLabel(self.main_frame, text="Archivo:")
        file_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        self.file_entry = ctk.CTkEntry(self.main_frame, width=400)
        self.file_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        self.browse_btn = ctk.CTkButton(
            self.main_frame,
            text="Examinar...",
            command=self.browse_file
        )
        self.browse_btn.grid(row=1, column=2, padx=5, pady=5)
        
        # Voice selection
        voice_label = ctk.CTkLabel(self.main_frame, text="Voz:")
        voice_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        
        self.voice_var = tk.StringVar()
        self.voice_dropdown = ctk.CTkComboBox(
            self.main_frame,
            variable=self.voice_var,
            values=[],  # Will be populated async
            width=400,
            state="readonly"
        )
        self.voice_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        # Buttons frame
        self.buttons_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.buttons_frame.grid(row=3, column=0, columnspan=3, pady=20)
        
        self.convert_btn = ctk.CTkButton(
            self.buttons_frame,
            text="Convertir a MP3",
            command=self.start_conversion,
            height=40,
            font=("Arial", 14, "bold")
        )
        self.convert_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ctk.CTkButton(
            self.buttons_frame,
            text="Pausar",
            command=self.toggle_pause,
            height=40,
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_btn = ctk.CTkButton(
            self.buttons_frame,
            text="Cancelar",
            command=self.cancel_conversion,
            height=40,
            fg_color="#8B0000",
            hover_color="#A52A2A",
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress frame
        self.progress_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.progress_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="")
        self.progress_label.pack(fill=tk.X, pady=5)
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.set(0)
        
        # Status bar
        self.status_var = tk.StringVar(value="Listo")
        self.status_bar = ctk.CTkLabel(
            self.main_frame,
            textvariable=self.status_var,
            anchor="w",
            height=20
        )
        self.status_bar.grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
    
    def load_voices_async(self):
        """Load voices in a background thread"""
        def _load():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.voice_manager.load_voices_async())
                
                # Update UI on the main thread
                self.after(0, self.update_voice_dropdown)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Error", 
                    f"No se pudieron cargar las voces: {str(e)}"
                ))
        
        threading.Thread(target=_load, daemon=True).start()
    
    def update_voice_dropdown(self):
        """Update the voice dropdown with available voices"""
        voices = self.voice_manager.get_voice_names()
        self.voice_dropdown.configure(values=voices)
        if voices:
            self.voice_dropdown.set(voices[0])
    
    def browse_file(self):
        """Open file dialog to select input file"""
        filetypes = [
            ("Archivos soportados", "*.pdf *.epub"),
            ("Archivos PDF", "*.pdf"),
            ("Archivos EPUB", "*.epub")
        ]
        
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            self.input_file = filename
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)
            
            # Set default output filename
            output_name = f"{Path(filename).stem}.mp3"
            self.output_file = str(Path(filename).parent / output_name)
    
    def toggle_pause(self):
        """Toggle pause/resume of the current conversion"""
        if self.audio_converter.is_paused:
            self.audio_converter.resume()
            self.pause_btn.configure(text="Pausar")
            self.status_var.set("Reanudando conversión...")
        else:
            self.audio_converter.pause()
            self.pause_btn.configure(text="Reanudar")
            self.status_var.set("Conversión en pausa...")
    
    def cancel_conversion(self):
        """Cancel the current conversion"""
        if messagebox.askyesno("Confirmar", "¿Estás seguro de que deseas cancelar la conversión?"):
            self.audio_converter.cancel()
            self.is_processing = False
            self.update_ui_state()
            self.status_var.set("Conversión cancelada")
    
    def start_conversion(self):
        """Start the conversion process"""
        if not self.input_file:
            messagebox.showerror("Error", "Por favor seleccione un archivo")
            return
            
        if not self.voice_var.get():
            messagebox.showerror("Error", "Por favor seleccione una voz")
            return
            
        self.is_processing = True
        self.update_ui_state()
        self.progress_bar.set(0)
        self.status_var.set("Extrayendo texto...")
        
        # Start conversion in a background thread
        self.conversion_thread = threading.Thread(
            target=self.run_conversion,
            daemon=True
        )
        self.conversion_thread.start()
    
    def update_ui_state(self):
        """Update UI elements based on current state"""
        if self.is_processing:
            self.convert_btn.configure(state=tk.DISABLED)
            self.browse_btn.configure(state=tk.DISABLED)
            self.voice_dropdown.configure(state=tk.DISABLED)
            self.pause_btn.configure(state=tk.NORMAL)
            self.cancel_btn.configure(state=tk.NORMAL)
        else:
            self.convert_btn.configure(state=tk.NORMAL)
            self.browse_btn.configure(state=tk.NORMAL)
            self.voice_dropdown.configure(state="readonly")
            self.pause_btn.configure(state=tk.DISABLED, text="Pausar")
            self.cancel_btn.configure(state=tk.DISABLED)
    
    def run_conversion(self):
        """Run the conversion process in a background thread"""
        try:
            # Get the appropriate extractor for the file type
            extractor = get_extractor(self.input_file)
            if not extractor:
                raise ValueError("Tipo de archivo no soportado")
            
            # Extract text
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            text = loop.run_until_complete(extractor.extract_text(self.input_file))
            
            if not text.strip():
                raise ValueError("No se pudo extraer texto del archivo")
            
            # Update UI
            self.after(0, lambda: self.status_var.set("Convirtiendo a voz..."))
            
            # Convert to speech
            def progress_callback(current: int, total: int):
                progress = current / total
                self.after(0, lambda: self.progress_bar.set(progress))
                self.after(0, lambda: self.status_var.set(
                    f"Procesando: {current}/{total} fragmentos"
                ))
            
            success = loop.run_until_complete(
                self.audio_converter.convert_text_to_speech(
                    text=text,
                    voice_name=self.voice_var.get(),
                    output_file=self.output_file,
                    progress_callback=progress_callback
                )
            )
            
            if success and not self.audio_converter.is_cancelled:
                self.after(0, self.on_conversion_complete)
            
        except Exception as e:
            self.after(0, lambda: self.on_conversion_error(str(e)))
        finally:
            self.is_processing = False
            self.after(0, self.update_ui_state)
    
    def on_conversion_complete(self):
        """Handle successful conversion"""
        self.progress_bar.set(1.0)
        self.status_var.set("¡Conversión completada con éxito!")
        messagebox.showinfo("Éxito", 
            f"El archivo se ha guardado como:\n{self.output_file}")
    
    def on_conversion_error(self, error_msg: str):
        """Handle conversion errors"""
        self.status_var.set("Error en la conversión")
        messagebox.showerror("Error", 
            f"Ocurrió un error durante la conversión:\n{error_msg}")
        self.progress_bar.set(0)
