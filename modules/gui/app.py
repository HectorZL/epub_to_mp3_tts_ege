import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import asyncio
import threading
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Set

import customtkinter as ctk

from modules.utils.voice_manager import VoiceManager
from modules.conversion.converter import AudioConverter
from modules.extractors import get_extractor

class ChapterSelectionDialog(ctk.CTkToplevel):
    def __init__(self, parent, chapters: List[str], title: str = "Seleccionar Capítulos", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.title(title)
        self.geometry("500x400")
        self.resizable(True, True)
        self.chapters = chapters
        self.selected_chapters: Set[int] = set(range(len(chapters)))  # All selected by default
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Title
        title_label = ctk.CTkLabel(
            self, 
            text="Seleccione los capítulos a convertir:",
            font=("Arial", 14, "bold")
        )
        title_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        # Scrollable frame for chapters
        self.chapters_frame = ctk.CTkScrollableFrame(self)
        self.chapters_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        
        # Chapter checkboxes
        self.checkbox_vars = []
        for i, chapter in enumerate(chapters):
            var = tk.BooleanVar(value=True)
            self.checkbox_vars.append(var)
            # Handle both string and dictionary chapter formats
            chapter_title = chapter.get('title', chapter) if isinstance(chapter, dict) else chapter
            cb = ctk.CTkCheckBox(
                self.chapters_frame,
                text=f"Capítulo {i+1}: {str(chapter_title)[:50]}{'...' if len(str(chapter_title)) > 50 else ''}",
                variable=var,
                command=lambda idx=i: self.toggle_chapter(idx)
            )
            cb.pack(anchor="w", pady=2)
        
        # Buttons frame
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=2, column=0, pady=10)
        
        select_all_btn = ctk.CTkButton(
            buttons_frame,
            text="Seleccionar Todo",
            command=self.select_all
        )
        select_all_btn.pack(side=tk.LEFT, padx=5)
        
        deselect_all_btn = ctk.CTkButton(
            buttons_frame,
            text="Deseleccionar Todo",
            command=self.deselect_all
        )
        deselect_all_btn.pack(side=tk.LEFT, padx=5)
        
        ok_btn = ctk.CTkButton(
            buttons_frame,
            text="Aceptar",
            command=self.on_ok
        )
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        self.result = None
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
    
    def toggle_chapter(self, idx: int):
        if idx in self.selected_chapters:
            self.selected_chapters.remove(idx)
        else:
            self.selected_chapters.add(idx)
    
    def select_all(self):
        self.selected_chapters = set(range(len(self.chapters)))
        for var in self.checkbox_vars:
            var.set(True)
    
    def deselect_all(self):
        self.selected_chapters.clear()
        for var in self.checkbox_vars:
            var.set(False)
    
    def on_ok(self):
        self.result = sorted(list(self.selected_chapters))
        self.destroy()
    
    def on_cancel(self):
        self.result = None
        self.destroy()

class TextToSpeechApp(ctk.CTk):
    def __init__(self, voice_manager: VoiceManager, audio_converter: AudioConverter):
        super().__init__()
        
        self.voice_manager = voice_manager
        self.audio_converter = audio_converter
        
        self.title("Conversor de Libros a Audio")
        self.geometry("900x700")
        ctk.set_appearance_mode("dark")
        
        self.input_file = ""
        self.output_file = ""
        self.is_processing = False
        self.conversion_thread: Optional[threading.Thread] = None
        self.selected_chapters: Optional[List[int]] = None
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.setup_ui()
        self.load_voices_async()
    
    def load_voices_async(self):
        """Load voices in a background thread to keep the UI responsive"""
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # This will load the voices into the voice manager
                loop.run_until_complete(self.voice_manager.load_voices_async())
                # Update the UI on the main thread
                self.after(100, self.update_voice_filters)
            except Exception as e:
                print(f"Error loading voices: {str(e)}")
            finally:
                loop.close()
        
        # Start the voice loading in a separate thread
        threading.Thread(target=run_async, daemon=True).start()
    
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
        
        # Voice selection frame
        voice_frame = ctk.CTkFrame(self.main_frame)
        voice_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        voice_frame.grid_columnconfigure(1, weight=1)
        
        # Language selection
        lang_label = ctk.CTkLabel(voice_frame, text="Idioma:")
        lang_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.lang_var = tk.StringVar()
        self.lang_dropdown = ctk.CTkComboBox(
            voice_frame,
            variable=self.lang_var,
            values=["Español", "Inglés", "Todos"],
            state="readonly",
            command=self.on_language_changed
        )
        self.lang_dropdown.set("Todos")
        self.lang_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # Gender selection
        gender_label = ctk.CTkLabel(voice_frame, text="Género:")
        gender_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        self.gender_var = tk.StringVar()
        self.gender_dropdown = ctk.CTkComboBox(
            voice_frame,
            variable=self.gender_var,
            values=["Masculino", "Femenino", "Todos"],
            state="readonly",
            command=self.on_gender_changed
        )
        self.gender_dropdown.set("Todos")
        self.gender_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        # Voice selection
        voice_label = ctk.CTkLabel(voice_frame, text="Voz:")
        voice_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        
        self.voice_var = tk.StringVar()
        self.voice_dropdown = ctk.CTkComboBox(
            voice_frame,
            variable=self.voice_var,
            values=[],  # Will be populated async
            state="readonly",
            width=400
        )
        self.voice_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        # Chapter selection button
        self.chapter_btn = ctk.CTkButton(
            self.main_frame,
            text="Seleccionar Capítulos",
            command=self.select_chapters,
            state=tk.DISABLED
        )
        self.chapter_btn.grid(row=3, column=0, columnspan=3, pady=10)
        
        # Buttons frame
        self.buttons_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.buttons_frame.grid(row=4, column=0, columnspan=3, pady=20)
        
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
        self.progress_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
        
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
        self.status_bar.grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
    
    def on_language_changed(self, event=None):
        """Update voice list when language changes"""
        self.update_voice_filters()
        
        # Update gender options based on selected language
        selected_lang = self.lang_var.get()
        lang_code = 'es' if selected_lang == 'Español' else 'en'
        
        # Get available genders for the selected language
        self.voice_manager._filter_voices(languages={lang_code})
        available_genders = self.voice_manager.get_available_genders()
        
        # Update gender combobox
        self.gender_dropdown['values'] = ['Todos'] + available_genders
        self.gender_dropdown.set('Todos')
        
        # Update voices
        self.update_voice_filters()
    
    def on_gender_changed(self, event=None):
        """Update voice list when gender changes"""
        self.update_voice_filters()
    
    def update_voice_filters(self):
        """Update voice list based on selected filters"""
        # Get selected language
        selected_lang = self.lang_var.get()
        lang_code = 'es' if selected_lang == 'Español' else 'en' if selected_lang == 'Inglés' else None
        
        # Get selected gender
        selected_gender = self.gender_var.get().lower()
        if selected_gender == 'todos':
            selected_gender = None
        
        # Update filters
        self.voice_manager.update_filters(language=lang_code, gender=selected_gender)
        
        # Update voice combobox
        voices = self.voice_manager.get_voice_names()
        self.voice_dropdown.configure(values=voices)
        
        # Try to keep the same voice if possible
        if voices and (self.voice_var.get() not in voices or not self.voice_var.get()):
            self.voice_var.set(voices[0])
        elif not voices:
            self.voice_var.set("")
    
    def select_chapters(self):
        """Show chapter selection dialog"""
        if not self.input_file:
            return
            
        # Get the appropriate extractor for the file type
        extractor = get_extractor(self.input_file)
        if not extractor:
            messagebox.showerror("Error", "Tipo de archivo no soportado")
            return
            
        try:
            # Run the async operation in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Get chapters from the file
            chapters = loop.run_until_complete(extractor.get_chapters(self.input_file))
            
            if not chapters:
                messagebox.showinfo("Información", "No se encontraron capítulos en el archivo.")
                return
                
            # Show chapter selection dialog
            dialog = ChapterSelectionDialog(
                parent=self,
                chapters=chapters,
                title="Seleccionar Capítulos"
            )
            
            # Wait for the dialog to close
            self.wait_window(dialog)
            
            # Update selected chapters if user clicked OK
            if hasattr(dialog, 'result') and dialog.result is not None:
                self.selected_chapters = dialog.result
                
                # Update button text to show selection
                total_chapters = len(chapters)
                selected_count = len(self.selected_chapters)
                
                if selected_count == total_chapters:
                    self.chapter_btn.configure(text="Todos los capítulos seleccionados")
                elif selected_count == 0:
                    self.chapter_btn.configure(text="Ningún capítulo seleccionado")
                    self.selected_chapters = None
                else:
                    self.chapter_btn.configure(text=f"{selected_count} de {total_chapters} capítulos seleccionados")
            
            loop.close()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar los capítulos: {str(e)}")
            print(f"Error in select_chapters: {e}")
    
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
            
            # Enable chapter selection button
            self.chapter_btn.configure(state=tk.NORMAL)
            
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
            self.lang_dropdown.configure(state=tk.DISABLED)
            self.gender_dropdown.configure(state=tk.DISABLED)
            self.chapter_btn.configure(state=tk.DISABLED)
            self.pause_btn.configure(state=tk.NORMAL)
            self.cancel_btn.configure(state=tk.NORMAL)
        else:
            self.convert_btn.configure(state=tk.NORMAL)
            self.browse_btn.configure(state=tk.NORMAL)
            self.voice_dropdown.configure(state="readonly")
            self.lang_dropdown.configure(state="readonly")
            self.gender_dropdown.configure(state="readonly")
            self.chapter_btn.configure(state=tk.NORMAL if self.input_file else tk.DISABLED)
            self.pause_btn.configure(state=tk.DISABLED, text="Pausar")
            self.cancel_btn.configure(state=tk.DISABLED)
    
    def run_conversion(self):
        """Run the conversion process in a background thread"""
        try:
            if not self.input_file or not self.output_file:
                return
                
            # Get the selected voice
            voice_name = self.voice_var.get()
            if not voice_name:
                messagebox.showerror("Error", "Por favor seleccione una voz")
                return
                
            # Update UI for conversion start
            self.is_processing = True
            self.update_ui_state()
            self.status_var.set("Procesando...")
            self.progress_bar.set(0)
            
            # Create a thread for the conversion
            self.conversion_thread = threading.Thread(
                target=self._run_conversion_thread,
                args=(self.input_file, self.output_file, voice_name)
            )
            self.conversion_thread.daemon = True
            self.conversion_thread.start()
            
        except Exception as e:
            self.is_processing = False
            self.update_ui_state()
            messagebox.showerror("Error", f"Error al iniciar la conversión: {str(e)}")
    
    def _run_conversion_thread(self, input_file: str, output_file: str, voice_name: str):
        """Run the actual conversion in a separate thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run the conversion
            loop.run_until_complete(self._convert_file(
                input_file, output_file, voice_name
            ))
            
            # Update UI on success
            self.after(0, self.on_conversion_complete)
            
        except Exception as error:
            # Store the error in a variable to avoid scoping issues
            error_msg = str(error)
            # Update UI on error
            self.after(0, lambda e=error_msg: self.on_conversion_error(e))
            
        finally:
            loop.close()
    
    async def _convert_file(self, input_file: str, output_file: str, voice_name: str):
        """Convert the file using the audio converter"""
        try:
            # Get the extractor for the file type
            extractor = get_extractor(input_file)
            if not extractor:
                raise ValueError("Formato de archivo no soportado")
            
            # Get the chapters or full content
            content = await extractor.extract_text(input_file)
            
            if not content:
                raise ValueError("No se pudo extraer contenido del archivo")
            
            # Handle both string and chapter-based content
            if isinstance(content, str):
                # Single file conversion
                await self.audio_converter.convert_text_to_speech(
                    content,
                    voice_name,
                    output_file,
                    progress_callback=self.progress_callback
                )
            elif isinstance(content, list) and content:
                # Chapter-based conversion
                total_chapters = len(content)
                
                # Filter chapters if selection exists
                if hasattr(self, 'selected_chapters') and self.selected_chapters is not None:
                    content = [content[i] for i in self.selected_chapters 
                             if 0 <= i < len(content)]
                
                # Convert each chapter
                for i, chapter in enumerate(content):
                    # Update progress
                    self.after(0, lambda i=i, total=len(content): 
                              self.progress_callback(i, total))
                    
                    # Create output filename for chapter
                    base, ext = os.path.splitext(output_file)
                    chapter_output = f"{base}_chapter{i+1}{ext}"
                    
                    # Convert this chapter
                    await self.audio_converter.convert_text_to_speech(
                        chapter.get('content', ''),
                        voice_name,
                        chapter_output,
                        progress_callback=lambda current, total, i=i: 
                            self.progress_callback(i + (current/total), len(content))
                    )
                    
        except Exception as e:
            raise Exception(f"Error en la conversión: {str(e)}")
    
    def progress_callback(self, current: int, total: int):
        """Update progress bar and status"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.set(current / total * 100)
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=f"Procesando: {current} de {total} capítulos...")
            
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
