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
        
        # Progress tracking
        self.show_detailed_progress = False
        self.current_chapter = 0
        self.total_chapters = 0
        self.total_characters = 0
        self.processed_characters = 0
        
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
        
        # Main progress bar
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.set(0)
        
        # Toggle button for detailed progress
        self.toggle_btn = ctk.CTkButton(
            self.progress_frame,
            text="▼ Mostrar detalles de progreso",
            font=("Arial", 10),
            fg_color="transparent",
            hover_color=("#f0f0f0", "#2b2b2b"),
            text_color=("gray10", "gray90"),
            command=self.toggle_detailed_progress,
            width=200,
            height=20
        )
        self.toggle_btn.pack(pady=(5, 0))
        
        # Detailed progress frame (initially hidden)
        self.detailed_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        
        # Chapter progress
        self.chapter_label = ctk.CTkLabel(
            self.detailed_frame,
            text="Capítulo: 0/0",
            anchor="w"
        )
        self.chapter_label.pack(fill=tk.X, pady=2)
        
        # Character progress
        self.char_label = ctk.CTkLabel(
            self.detailed_frame,
            text="Caracteres: 0/0 (0%)",
            anchor="w"
        )
        self.char_label.pack(fill=tk.X, pady=2)
        
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
            # Reset progress tracking at start of conversion
            self.after(0, self.reset_ui_state)
            
            # Get the extractor for the file type
            extractor = get_extractor(input_file)
            if not extractor:
                raise ValueError("Formato de archivo no soportado")
            
            # Get the chapters or full content
            content = await extractor.extract_text(input_file)
            
            if not content:
                raise ValueError("No se pudo extraer contenido del archivo")
            
            # Calculate total chapters and characters
            if isinstance(content, list):
                self.total_chapters = len(content)
                total_chars = sum(
                    len(chapter.get('content', '') if isinstance(chapter, dict) else str(chapter))
                    for chapter in content
                )
                self.after(0, lambda: self.update_progress_ui(total_chapters=self.total_chapters, total_chars=total_chars))
            else:
                total_chars = len(content)
                self.after(0, lambda: self.update_progress_ui(total_chars=total_chars))
            
            # Handle both string and chapter-based content
            if isinstance(content, str) or not hasattr(self, 'selected_chapters') or self.selected_chapters is None:
                # Single file conversion - combine all content
                if isinstance(content, list):
                    combined_content = '\n\n'.join(
                        chapter.get('content', '') if isinstance(chapter, dict) else str(chapter)
                        for chapter in content
                    )
                    total_chars = sum(
                        len(chapter.get('content', '') if isinstance(chapter, dict) else str(chapter))
                        for chapter in content
                    )
                else:
                    combined_content = content
                    total_chars = len(combined_content)
                
                # Update total characters
                self.after(0, lambda: self.progress_callback(0, 1, 0, total_chars, 1))
                
                await self.audio_converter.convert_text_to_speech(
                    combined_content,
                    voice_name,
                    output_file,
                    progress_callback=lambda current, total, chars=0, total_chars=total_chars: 
                        self.progress_callback(
                            current/total if total > 0 else 0, 
                            1, 
                            int((current/total) * total_chars) if total > 0 else 0, 
                            total_chars,
                            1
                        )
                )
            elif isinstance(content, list) and content:
                # Chapter-based conversion - process each chapter separately
                # Filter chapters if selection exists
                if hasattr(self, 'selected_chapters') and self.selected_chapters is not None:
                    content = [content[i] for i in self.selected_chapters 
                             if 0 <= i < len(content)]
                    self.total_chapters = len(content)
                    self.after(0, lambda: self.update_progress_ui(total_chars=total_chars))
                
                self.current_chapter = 0
                
                # Convert each chapter
                for i, chapter in enumerate(content):
                    self.current_chapter = i + 1
                    
                    # Get chapter content and character count
                    chapter_content = chapter.get('content', '') if isinstance(chapter, dict) else str(chapter)
                    chapter_chars = len(chapter_content)
                    
                    # Update progress for new chapter
                    processed_before = sum(
                        len(c.get('content', '') if isinstance(c, dict) else str(c))
                        for c in content[:i]
                    )
                    self.after(0, lambda i=i, total=len(content), current_chars=processed_before: 
                        self.progress_callback(
                            i, 
                            total,
                            current_chars,
                            total_chars,
                            i + 1
                        )
                    )
                    
                    # Create output filename for chapter using the original chapter number
                    base, ext = os.path.splitext(output_file)
                    # Get the original chapter number from selected_chapters if available
                    chapter_num = self.selected_chapters[i] + 1 if hasattr(self, 'selected_chapters') and self.selected_chapters else (i + 1)
                    chapter_output = f"{base}_capitulo{chapter_num:02d}{ext}"
                    
                    # Convert this chapter
                    processed_before = sum(
                        len(c.get('content', '') if isinstance(c, dict) else str(c))
                        for c in content[:i]
                    )
                    await self.audio_converter.convert_text_to_speech(
                        chapter_content,
                        voice_name,
                        chapter_output,
                        progress_callback=lambda current, total, i=i, chapter_chars=chapter_chars, 
                            processed_before=processed_before: 
                            self.progress_callback(
                                i + (current/total if total > 0 else 0), 
                                len(content),
                                processed_before + int((current/total) * chapter_chars) if total > 0 else 0,
                                total_chars,
                                i + 1
                            )
                    )
                    
        except Exception as e:
            raise Exception(f"Error en la conversión: {str(e)}")
    
    def update_progress_ui(self, total_chapters=0, total_chars=0):
        """Update the progress UI with total information"""
        if total_chapters > 0:
            self.total_chapters = total_chapters
            self.chapter_label.configure(text=f"Capítulo: 0/{self.total_chapters}")
        
        if total_chars > 0:
            self.total_characters = total_chars
            self.char_label.configure(text=f"Caracteres: 0/{total_chars:,} (0%)")
    
    def progress_callback(self, current: float, total: int, current_chars: int = 0, total_chars: int = 0, chapter: int = 0):
        """Update progress bar and status with detailed information"""
        # Ensure we're updating the UI in the main thread
        def update_ui():
            try:
                # Update progress bar
                progress = current / total if total > 0 else 0
                self.progress_bar.set(progress)
                
                # Update chapter information
                if chapter > 0:
                    self.current_chapter = chapter
                    if hasattr(self, 'total_chapters'):
                        self.chapter_label.configure(text=f"Capítulo: {self.current_chapter}/{self.total_chapters}")
                
                # Update character information
                if total_chars > 0:
                    self.processed_characters = current_chars
                    self.total_characters = total_chars
                    percent = (current_chars / total_chars * 100) if total_chars > 0 else 0
                    self.char_label.configure(
                        text=f"Caracteres: {current_chars:,}/{total_chars:,} ({percent:.1f}%)"
                    )
                
                # Update status
                if hasattr(self, 'status_var'):
                    if hasattr(self, 'total_chapters') and self.total_chapters > 0:
                        self.status_var.set(
                            f"Procesando capítulo {self.current_chapter} de {self.total_chapters}... "
                            f"({self.processed_characters:,}/{self.total_characters:,} caracteres)"
                        )
                    else:
                        self.status_var.set(f"Procesando... {int(current)} de {int(total)}")
                        
                # Force update the UI
                self.update_idletasks()
                
            except Exception as e:
                print(f"Error updating UI: {e}")
        
        # Schedule the UI update on the main thread
        self.after(0, update_ui)

    def toggle_detailed_progress(self):
        """Toggle the visibility of the detailed progress section"""
        if self.show_detailed_progress:
            self.detailed_frame.pack_forget()
            self.toggle_btn.configure(text="▼ Mostrar detalles de progreso")
        else:
            self.detailed_frame.pack(fill=tk.X, pady=(5, 0))
            self.toggle_btn.configure(text="▲ Ocultar detalles de progreso")
        self.show_detailed_progress = not self.show_detailed_progress

    def reset_ui_state(self):
        """Reset the UI to its initial state"""
        self.progress_bar.set(0)
        self.status_var.set("Listo")
        self.current_chapter = 0
        self.total_chapters = 0
        self.processed_characters = 0
        self.total_characters = 0
        self.chapter_label.configure(text="Capítulo: 0/0")
        self.char_label.configure(text="Caracteres: 0/0 (0%)")
        self.is_processing = False
        self.conversion_thread = None
        self.update_ui_state()

    def on_conversion_complete(self):
        """Handle successful conversion"""
        self.progress_bar.set(1.0)
        self.status_var.set("¡Conversión completada con éxito!")
        messagebox.showinfo("Éxito", "La conversión se ha completado correctamente.")
        # Reset the UI after a short delay to show the success message
        self.after(2000, self.reset_ui_state)
    
    def on_conversion_error(self, error_msg: str):
        """Handle conversion errors"""
        self.status_var.set("Error en la conversión")
        messagebox.showerror("Error", 
            f"Ocurrió un error durante la conversión:\n{error_msg}")
        self.progress_bar.set(0)
