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



class TextToSpeechApp(ctk.CTk):
    def __init__(self, voice_manager: VoiceManager, audio_converter: AudioConverter, piper_manager=None, chatterbox_manager=None, kokoro_manager=None):
        super().__init__()
        
        self.voice_manager = voice_manager
        self.audio_converter = audio_converter
        self.piper_manager = piper_manager
        self.chatterbox_manager = chatterbox_manager
        self.kokoro_manager = kokoro_manager
        
        self.title("Conversor de Libros a Audio")
        self.geometry("900x780")
        ctk.set_appearance_mode("dark")
        
        self.input_file = ""
        self.output_file = ""
        self.output_files_created: List[str] = []
        self.output_format_var = tk.StringVar(value="MP3 — comprimido (~0.5–1.5 MB/min)")
        self.is_processing = False
        self.conversion_thread: Optional[threading.Thread] = None
        self.selected_chapters: Optional[List[int]] = None
        
        # Engine mode: 'online' | 'offline'
        self.engine_mode = tk.StringVar(value="online")
        
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
        # Configure window background
        self.configure(fg_color="#0F172A")
        
        # Outer container to center the app and prevent infinite stretching on maximize
        self.outer_container = ctk.CTkFrame(self, fg_color="transparent")
        self.outer_container.grid(row=0, column=0, sticky="ns")
        self.outer_container.grid_columnconfigure(0, weight=1)
        
        # Configure grid for main window to expand around outer_container
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Main container
        self.main_frame = ctk.CTkFrame(self.outer_container, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, padx=20, pady=15, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)

        # ── Title Block ────────────────────────────────────────────────────────
        title_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, pady=(10, 20), sticky="ew")
        title_frame.grid_columnconfigure(0, weight=1)
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="🎧 AudioBook Studio",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#F8FAFC"
        )
        title_label.grid(row=0, column=0)
        
        subtitle_label = ctk.CTkLabel(
            title_frame,
            text="Convierte tus libros electrónicos (EPUB, PDF) a audiolibros realistas mediante IA local u online",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#64748B"
        )
        subtitle_label.grid(row=1, column=0, pady=(2, 0))

        # ── Card 1: Motor TTS (row 2) ──────────────────────────────────────────
        engine_card = ctk.CTkFrame(
            self.main_frame,
            fg_color="#1E293B",
            corner_radius=12,
            border_color="#334155",
            border_width=1
        )
        engine_card.grid(row=2, column=0, padx=5, pady=8, sticky="ew")
        engine_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            engine_card,
            text="⚡ Motor de Voz (TTS):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#E2E8F0"
        ).grid(row=0, column=0, padx=15, pady=15, sticky="w")

        toggle_inner = ctk.CTkFrame(engine_card, fg_color="transparent")
        toggle_inner.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.btn_online = ctk.CTkButton(
            toggle_inner, text="Online (edge-tts)", width=140, height=32,
            command=lambda: self._set_engine("online")
        )
        self.btn_online.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_offline = ctk.CTkButton(
            toggle_inner, text="Offline (Piper)", width=140, height=32,
            command=lambda: self._set_engine("offline")
        )
        self.btn_offline.pack(side=tk.LEFT)

        self.btn_chatterbox = ctk.CTkButton(
            toggle_inner, text="Offline (Chatterbox)", width=140, height=32,
            command=lambda: self._set_engine("chatterbox")
        )
        self.btn_chatterbox.pack(side=tk.LEFT, padx=(6, 0))

        self.btn_kokoro = ctk.CTkButton(
            toggle_inner, text="Offline (Kokoro)", width=140, height=32,
            command=lambda: self._set_engine("kokoro")
        )
        self.btn_kokoro.pack(side=tk.LEFT, padx=(6, 0))

        self.engine_badge = ctk.CTkLabel(
            engine_card, text="● Online", text_color="#10B981",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        )
        self.engine_badge.grid(row=0, column=2, padx=15)

        # ── Card 2: File selection (row 3) ──────────────────────────────────────
        file_card = ctk.CTkFrame(
            self.main_frame,
            fg_color="#1E293B",
            corner_radius=12,
            border_color="#334155",
            border_width=1
        )
        file_card.grid(row=3, column=0, padx=5, pady=8, sticky="ew")
        file_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            file_card,
            text="📁 Libro de Origen:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#E2E8F0"
        ).grid(row=0, column=0, padx=15, pady=15, sticky="w")

        self.file_entry = ctk.CTkEntry(
            file_card,
            placeholder_text="Selecciona un archivo EPUB o PDF para comenzar...",
            height=36,
            fg_color="#0F172A",
            border_color="#334155",
            border_width=1,
            text_color="#F1F5F9",
            corner_radius=8
        )
        self.file_entry.grid(row=0, column=1, padx=5, pady=12, sticky="ew")

        self.browse_btn = ctk.CTkButton(
            file_card,
            text="Examinar...",
            command=self.browse_file,
            height=36,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#F1F5F9",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8
        )
        self.browse_btn.grid(row=0, column=2, padx=15, pady=12)

        # ── Card 3: Configuration panels (row 4) ─────────────────────────────────
        self.config_card = ctk.CTkFrame(
            self.main_frame,
            fg_color="#1E293B",
            corner_radius=12,
            border_color="#334155",
            border_width=1
        )
        self.config_card.grid(row=4, column=0, padx=5, pady=8, sticky="ew")
        self.config_card.grid_columnconfigure(0, weight=1)

        # ── Online panel (edge-tts) ──
        self.online_panel = ctk.CTkFrame(self.config_card, fg_color="transparent")
        self.online_panel.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        self.online_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.online_panel,
            text="🎙️ Configuración de Voz (Online Edge-TTS)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#F8FAFC"
        ).grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")

        ctk.CTkLabel(self.online_panel, text="Idioma:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=5, pady=6, sticky="w")
        self.lang_var = tk.StringVar()
        self.lang_dropdown = ctk.CTkComboBox(
            self.online_panel, variable=self.lang_var,
            values=["Español", "Inglés", "Todos"],
            state="readonly", command=self.on_language_changed,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8
        )
        self.lang_dropdown.set("Español")
        self.lang_dropdown.grid(row=1, column=1, padx=5, pady=6, sticky="w")

        ctk.CTkLabel(self.online_panel, text="Género:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=5, pady=6, sticky="w")
        self.gender_var = tk.StringVar()
        self.gender_dropdown = ctk.CTkComboBox(
            self.online_panel, variable=self.gender_var,
            values=["Masculino", "Femenino", "Todos"],
            state="readonly", command=self.on_gender_changed,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8
        )
        self.gender_dropdown.set("Femenino")
        self.gender_dropdown.grid(row=2, column=1, padx=5, pady=6, sticky="w")

        ctk.CTkLabel(self.online_panel, text="Voz:", font=ctk.CTkFont(size=12)).grid(row=3, column=0, padx=5, pady=6, sticky="w")
        self.voice_var = tk.StringVar()
        self.voice_dropdown = ctk.CTkComboBox(
            self.online_panel, variable=self.voice_var,
            values=[], state="readonly", width=400,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8
        )
        self.voice_dropdown.grid(row=3, column=1, padx=5, pady=6, sticky="w")

        # ── Offline panel (Piper) ──
        self.offline_panel = ctk.CTkFrame(self.config_card, fg_color="transparent")
        self.offline_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.offline_panel,
            text="🎙️ Configuración de Voz (Piper TTS)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#F8FAFC"
        ).grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky="w")

        ctk.CTkLabel(self.offline_panel, text="Idioma:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=5, pady=6, sticky="w")
        self.piper_lang_var = tk.StringVar(value="Español")
        self.piper_lang_dropdown = ctk.CTkComboBox(
            self.offline_panel,
            variable=self.piper_lang_var,
            values=["Español", "Inglés", "Todos"],
            state="readonly",
            command=self._update_piper_voices,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8
        )
        self.piper_lang_dropdown.grid(row=1, column=1, padx=5, pady=6, sticky="w")

        self.piper_gender_var = tk.StringVar(value="Todos")
        
        ctk.CTkLabel(self.offline_panel, text="Voz Piper:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=5, pady=6, sticky="w")
        self.piper_voice_var = tk.StringVar()
        self.piper_voice_dropdown = ctk.CTkComboBox(
            self.offline_panel,
            variable=self.piper_voice_var,
            values=[], state="readonly", width=350,
            command=self._on_piper_voice_selected,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8
        )
        self.piper_voice_dropdown.grid(row=2, column=1, padx=5, pady=6, sticky="w")

        self.piper_dl_btn = ctk.CTkButton(
            self.offline_panel,
            text="Descargar modelo",
            width=140,
            fg_color="#F97316",
            hover_color="#EA580C",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._download_piper_model
        )
        self.piper_dl_btn.grid(row=2, column=2, padx=10, pady=6)

        self.piper_status_lbl = ctk.CTkLabel(
            self.offline_panel,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        self.piper_status_lbl.grid(row=3, column=0, columnspan=3, padx=5, pady=4, sticky="w")

        self.piper_dl_bar = ctk.CTkProgressBar(self.offline_panel, mode="determinate", fg_color="#0F172A", progress_color="#4F46E5", height=8)
        self.piper_dl_bar.grid(row=4, column=0, columnspan=3, padx=5, pady=(4, 6), sticky="ew")
        self.piper_dl_bar.set(0)
        self.piper_dl_bar.grid_remove()

        # Initialize Piper voice list
        self._update_piper_voices()

        # ── Chatterbox panel (Chatterbox) ──
        self.chatterbox_panel = ctk.CTkFrame(self.config_card, fg_color="transparent")
        self.chatterbox_panel.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            self.chatterbox_panel,
            text="🎙️ Configuración de Voz (Chatterbox local)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#F8FAFC"
        ).grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky="w")

        self.cb_status_lbl = ctk.CTkLabel(
            self.chatterbox_panel,
            text="Verificando componentes...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        self.cb_status_lbl.grid(row=1, column=0, columnspan=2, padx=5, pady=4, sticky="w")

        self.cb_install_btn = ctk.CTkButton(
            self.chatterbox_panel,
            text="Instalar componentes de IA local",
            width=220,
            fg_color="#F97316",
            hover_color="#EA580C",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._install_chatterbox_dependencies
        )
        self.cb_install_btn.grid(row=1, column=2, padx=10, pady=4, sticky="e")

        ctk.CTkLabel(self.chatterbox_panel, text="Voz Chatterbox:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=5, pady=6, sticky="w")
        self.cb_voice_mode_var = tk.StringVar(value="Voz Predeterminada")
        self.cb_voice_dropdown = ctk.CTkComboBox(
            self.chatterbox_panel,
            variable=self.cb_voice_mode_var,
            values=["Voz Predeterminada", "Clonada (Personalizada...)"],
            state="readonly",
            width=200,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8,
            command=self._on_cb_voice_mode_changed
        )
        self.cb_voice_dropdown.grid(row=2, column=1, padx=5, pady=6, sticky="w")

        self.cb_clone_frame = ctk.CTkFrame(self.chatterbox_panel, fg_color="transparent")
        self.cb_clone_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.cb_clone_frame, text="Audio de Referencia (~10s):", font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=5, pady=4, sticky="w")
        self.cb_ref_audio_entry = ctk.CTkEntry(
            self.cb_clone_frame, width=280,
            fg_color="#0F172A", border_color="#334155", border_width=1, text_color="#F1F5F9", corner_radius=8
        )
        self.cb_ref_audio_entry.grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        
        self.cb_ref_browse_btn = ctk.CTkButton(
            self.cb_clone_frame,
            text="Examinar...",
            width=90,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#F1F5F9",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=8,
            command=self._browse_ref_audio
        )
        self.cb_ref_browse_btn.grid(row=0, column=2, padx=5, pady=4)

        # ── Kokoro panel (Kokoro) ──
        self.kokoro_panel = ctk.CTkFrame(self.config_card, fg_color="transparent")
        self.kokoro_panel.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            self.kokoro_panel,
            text="🎙️ Configuración de Voz (Kokoro local)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#F8FAFC"
        ).grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky="w")

        self.kokoro_status_lbl = ctk.CTkLabel(
            self.kokoro_panel,
            text="Verificando componentes...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        self.kokoro_status_lbl.grid(row=1, column=0, columnspan=2, padx=5, pady=4, sticky="w")

        self.kokoro_dl_btn = ctk.CTkButton(
            self.kokoro_panel,
            text="Descargar modelo Kokoro (~180MB)",
            width=260,
            fg_color="#F97316",
            hover_color="#EA580C",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._download_kokoro_model
        )
        self.kokoro_dl_btn.grid(row=1, column=2, padx=10, pady=4, sticky="e")

        ctk.CTkLabel(self.kokoro_panel, text="Idioma:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=5, pady=6, sticky="w")
        self.kokoro_lang_var = tk.StringVar(value="Español")
        self.kokoro_lang_dropdown = ctk.CTkComboBox(
            self.kokoro_panel,
            variable=self.kokoro_lang_var,
            values=["Español", "Inglés"],
            state="readonly",
            width=120,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8,
            command=self._update_kokoro_voices
        )
        self.kokoro_lang_dropdown.grid(row=2, column=1, padx=5, pady=6, sticky="w")

        ctk.CTkLabel(self.kokoro_panel, text="Voz Kokoro:", font=ctk.CTkFont(size=12)).grid(row=3, column=0, padx=5, pady=6, sticky="w")
        self.kokoro_voice_var = tk.StringVar()
        self.kokoro_voice_dropdown = ctk.CTkComboBox(
            self.kokoro_panel,
            variable=self.kokoro_voice_var,
            values=[],
            state="readonly",
            width=260,
            fg_color="#0F172A", border_color="#334155", button_color="#1E293B", button_hover_color="#334155", corner_radius=8
        )
        self.kokoro_voice_dropdown.grid(row=3, column=1, columnspan=2, padx=5, pady=6, sticky="ew")

        self.kokoro_dl_bar = ctk.CTkProgressBar(self.kokoro_panel, mode="determinate", fg_color="#0F172A", progress_color="#4F46E5", height=8)
        self.kokoro_dl_bar.grid(row=4, column=0, columnspan=3, padx=5, pady=(4, 8), sticky="ew")
        self.kokoro_dl_bar.set(0)
        self.kokoro_dl_bar.grid_remove()
        
        self._update_kokoro_voices()

        # ── Chapter Selection Collapsible (row 5) ──────────────────────────────
        self.chapter_toggle_btn = ctk.CTkButton(
            self.main_frame,
            text="📖 Mostrar Capítulos (No hay archivo cargado)",
            command=self.toggle_chapter_panel,
            state=tk.DISABLED,
            height=36,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#F1F5F9",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8
        )
        self.chapter_toggle_btn.grid(row=5, column=0, pady=(10, 5), sticky="ew")

        # Container for chapters checkboxes (hidden by default)
        self.chapter_container = ctk.CTkFrame(
            self.main_frame,
            fg_color="#1E293B",
            corner_radius=12,
            border_color="#334155",
            border_width=1
        )
        
        # Header with select all/deselect all
        ctrl_frame = ctk.CTkFrame(self.chapter_container, fg_color="transparent")
        ctrl_frame.pack(fill=tk.X, padx=15, pady=8)
        
        ctk.CTkButton(
            ctrl_frame, text="Seleccionar todo", width=120, height=26,
            fg_color="#334155", hover_color="#475569", text_color="#F1F5F9",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6, command=self._select_all_chapters
        ).pack(side=tk.LEFT, padx=2)
        
        ctk.CTkButton(
            ctrl_frame, text="Deseleccionar todo", width=120, height=26,
            fg_color="#334155", hover_color="#475569", text_color="#F1F5F9",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6, command=self._deselect_all_chapters
        ).pack(side=tk.LEFT, padx=2)
        
        self.chapter_scroll_frame = ctk.CTkScrollableFrame(self.chapter_container, height=180, fg_color="#0F172A", corner_radius=8)
        self.chapter_scroll_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        # ── Card 4: Progress & Controls (row 7) ──────────────────────────────────
        progress_card = ctk.CTkFrame(
            self.main_frame,
            fg_color="#1E293B",
            corner_radius=12,
            border_color="#334155",
            border_width=1
        )
        progress_card.grid(row=7, column=0, padx=5, pady=8, sticky="ew")
        progress_card.grid_columnconfigure(0, weight=1)

        # Checkboxes for merging and keeping chapters (row 0)
        self.options_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        self.options_frame.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        # Output format selector. MP3 works with online and offline engines;
        # WAV/FLAC are available for locally generated audio.
        self.format_label = ctk.CTkLabel(
            self.options_frame,
            text="Formato:",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#E2E8F0"
        )
        self.format_label.pack(side=tk.LEFT, padx=(0, 6))

        self.output_format_dropdown = ctk.CTkComboBox(
            self.options_frame,
            variable=self.output_format_var,
            values=[
                "MP3 — comprimido (~0.5–1.5 MB/min)",
                "WAV — sin pérdida (~2.5–3 MB/min)",
                "FLAC — sin pérdida (~0.8–2 MB/min)",
            ],
            state="readonly",
            width=220,
            command=self._on_output_format_changed,
            fg_color="#0F172A",
            border_color="#334155",
            button_color="#1E293B",
            button_hover_color="#334155",
            corner_radius=8,
        )
        self.output_format_dropdown.pack(side=tk.LEFT, padx=(0, 18))

        self.join_chapters_var = tk.BooleanVar(value=True)
        self.join_checkbox = ctk.CTkCheckBox(
            self.options_frame,
            text="Unir capítulos al finalizar",
            variable=self.join_chapters_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#E2E8F0",
            command=self._on_join_chapters_changed
        )
        self.join_checkbox.pack(side=tk.LEFT, padx=(0, 20))

        self.keep_chapters_var = tk.BooleanVar(value=True)
        self.keep_checkbox = ctk.CTkCheckBox(
            self.options_frame,
            text="Conservar capítulos individuales sueltos",
            variable=self.keep_chapters_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#E2E8F0"
        )
        self.keep_checkbox.pack(side=tk.LEFT)

        # Action Buttons inside progress card to unify look (row 1)
        self.buttons_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        self.buttons_frame.grid(row=1, column=0, padx=15, pady=(5, 15), sticky="ew")
        self.buttons_frame.grid_columnconfigure(0, weight=1)
        self.buttons_frame.grid_columnconfigure(1, weight=1)

        self.convert_btn = ctk.CTkButton(
            self.buttons_frame, text="🚀 Convertir a MP3",
            command=self.start_conversion, height=42,
            fg_color="#10B981", hover_color="#059669",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=8
        )
        self.convert_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            self.buttons_frame, text="🛑 Cancelar",
            command=self.cancel_conversion, height=42,
            fg_color="#EF4444", hover_color="#DC2626",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=8
        )
        self.cancel_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # Progress bar (row 2)
        self.progress_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, mode="determinate", fg_color="#0F172A", progress_color="#4F46E5", height=10)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.set(0)

        self.toggle_btn = ctk.CTkButton(
            self.progress_frame, text="▼ Mostrar detalles de progreso",
            font=ctk.CTkFont(family="Segoe UI", size=11), fg_color="transparent",
            hover_color=("#f0f0f0", "#2b2b2b"),
            text_color="#94A3B8",
            command=self.toggle_detailed_progress, width=200, height=20
        )
        self.toggle_btn.pack(pady=(5, 0))

        self.detailed_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")

        self.chapter_label = ctk.CTkLabel(
            self.detailed_frame, text="📖 Capítulo: 0/0", anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#E2E8F0"
        )
        self.chapter_label.pack(fill=tk.X, pady=2)

        self.char_label = ctk.CTkLabel(
            self.detailed_frame, text="🔤 Caracteres: 0/0 (0%)", anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#E2E8F0"
        )
        self.char_label.pack(fill=tk.X, pady=2)

        # ── Status bar (row 8) ──────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Listo")
        self.status_bar = ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor="w", height=20,
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#64748B"
        )
        self.status_bar.grid(row=8, column=0, padx=5, pady=(5, 0), sticky="ew")

        # ── Footer ─────────────────────────────────────────────────────────────
        self.footer_frame = ctk.CTkFrame(self.outer_container, height=25, fg_color="transparent")
        self.footer_frame.grid(row=1, column=0, sticky="sew", padx=20, pady=(0, 10))
        self.outer_container.grid_rowconfigure(0, weight=1)
        self.outer_container.grid_rowconfigure(1, weight=0)

        self.dev_credit = ctk.CTkLabel(
            self.footer_frame, text="Desarrollado con ❤ para EGE",
            text_color="#475569", font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic")
        )
        self.dev_credit.pack(side=tk.LEFT)

        self.github_link = ctk.CTkLabel(
            self.footer_frame, text="GitHub",
            text_color="#6366F1",
            cursor="hand2", font=ctk.CTkFont(family="Segoe UI", size=10, underline=True)
        )
        self.github_link.pack(side=tk.RIGHT)
        self.github_link.bind("<Button-1>", lambda e: self.open_github())
        self.footer_frame.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Set initial styles for the active engine button
        self._update_engine_button_styles()

    # ─── Engine toggle helpers ─────────────────────────────────────────────────

    def _update_engine_button_styles(self):
        """Actualiza visualmente los botones del selector de motor según el estado activo."""
        mode = self.engine_mode.get()
        for btn, key in [
            (self.btn_online, "online"),
            (self.btn_offline, "offline"),
            (self.btn_chatterbox, "chatterbox"),
            (self.btn_kokoro, "kokoro")
        ]:
            if mode == key:
                btn.configure(
                    fg_color="#4F46E5",
                    text_color="#FFFFFF",
                    hover_color="#4338CA",
                    border_width=0,
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
                )
            else:
                btn.configure(
                    fg_color="#0F172A",
                    text_color="#94A3B8",
                    hover_color="#1E293B",
                    border_width=1,
                    border_color="#334155",
                    font=ctk.CTkFont(family="Segoe UI", size=12)
                )

    def _on_join_chapters_changed(self):
        """Enable/disable keep checkbox depending on join chapters selection"""
        if self.join_chapters_var.get():
            self.keep_checkbox.configure(state=tk.NORMAL)
        else:
            self.keep_chapters_var.set(True)
            self.keep_checkbox.configure(state=tk.DISABLED)

    def _set_engine(self, mode: str):
        """Switch between 'online', 'offline' (Piper), 'chatterbox' and 'kokoro' engine."""
        self.engine_mode.set(mode)
        self.audio_converter.engine_mode = mode

        # Ocultar todos
        self.online_panel.grid_remove()
        self.offline_panel.grid_remove()
        self.chatterbox_panel.grid_remove()
        if hasattr(self, 'kokoro_panel'):
            self.kokoro_panel.grid_remove()

        # Update button styles dynamically
        self._update_engine_button_styles()

        if mode == "online":
            self.engine_badge.configure(text="● Online", text_color="#10B981")
            self.online_panel.grid(row=1, column=0, columnspan=3, padx=15, pady=15, sticky="ew")
        elif mode == "offline":
            self.engine_badge.configure(text="● Offline (Piper)", text_color="#F97316")
            self.offline_panel.grid(row=1, column=0, columnspan=3, padx=15, pady=15, sticky="ew")
        elif mode == "chatterbox":
            self.engine_badge.configure(text="● Chatterbox IA", text_color="#A855F7")
            self.chatterbox_panel.grid(row=1, column=0, columnspan=3, padx=15, pady=15, sticky="ew")
            self._check_chatterbox_status()
        elif mode == "kokoro":
            self.engine_badge.configure(text="● Kokoro IA", text_color="#10B981")
            self.kokoro_panel.grid(row=1, column=0, columnspan=3, padx=15, pady=15, sticky="ew")
            self._check_kokoro_status()

    # ─── Chatterbox panel helpers ──────────────────────────────────────────────

    def _check_chatterbox_status(self):
        """Verifica si Chatterbox está instalado y actualiza la UI."""
        if not self.chatterbox_manager:
            return
            
        if self.chatterbox_manager.is_available():
            has_cuda = self.chatterbox_manager.check_cuda()
            device_str = "GPU (CUDA)" if has_cuda else "CPU"
            self.cb_status_lbl.configure(
                text=f"Componentes listos. Dispositivo de IA: {device_str}",
                text_color="#4CAF50"
            )
            self.cb_install_btn.grid_remove()
            self.cb_voice_dropdown.configure(state="readonly")
        else:
            self.cb_status_lbl.configure(
                text="Faltan dependencias de IA local (chatterbox-tts, torch, torchaudio)",
                text_color="#F44336"
            )
            self.cb_install_btn.grid()
            self.cb_voice_dropdown.configure(state=tk.DISABLED)
            self.cb_clone_frame.grid_remove()

    def _install_chatterbox_dependencies(self):
        """Instala las dependencias en segundo plano para no congelar la UI."""
        self.cb_install_btn.configure(state=tk.DISABLED, text="Instalando...")
        
        log_win = ctk.CTkToplevel(self)
        log_win.title("Instalador de componentes de IA")
        log_win.geometry("600x400")
        log_win.grid_columnconfigure(0, weight=1)
        log_win.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(log_win, text="Instalando PyTorch, torchaudio y chatterbox-tts...", font=("Arial", 12, "bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        log_text = tk.Text(log_win, wrap=tk.WORD, bg="#2B2B2B", fg="#FFFFFF", insertbackground="white")
        log_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(log_text, command=log_text.yview)
        log_text.configure(yscrollcommand=scrollbar.set)
        
        def write_log(message):
            def _write():
                log_text.insert(tk.END, message + "\n")
                log_text.see(tk.END)
            self.after(0, _write)

        def _run():
            success = self.chatterbox_manager.install_dependencies(progress_callback=write_log)
            if success:
                self.after(0, lambda: (
                    self._check_chatterbox_status(),
                    messagebox.showinfo("Instalación Completada", "Todos los componentes se instalaron correctamente.")
                ))
            else:
                self.after(0, lambda: (
                    self.cb_install_btn.configure(state=tk.NORMAL, text="Reintentar instalación"),
                    self._check_chatterbox_status(),
                    messagebox.showerror("Error de instalación", "Ocurrió un error al instalar los componentes. Revisa la consola.")
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _on_cb_voice_mode_changed(self, choice):
        """Muestra u oculta la sección de clonación según la elección."""
        if choice == "Clonada (Personalizada...)":
            self.cb_clone_frame.grid(row=3, column=0, columnspan=3, padx=5, pady=4, sticky="ew")
        else:
            self.cb_clone_frame.grid_remove()

    def _browse_ref_audio(self):
        """Busca el archivo de audio de referencia para clonación."""
        filetypes = [
            ("Archivos de audio", "*.wav *.mp3"),
            ("Archivos WAV", "*.wav"),
            ("Archivos MP3", "*.mp3")
        ]
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            self.cb_ref_audio_entry.delete(0, tk.END)
            self.cb_ref_audio_entry.insert(0, filename)

    # ─── Piper panel helpers ───────────────────────────────────────────────────

    def _update_piper_voices(self, event=None):
        """Refresh Piper voice list based on selected lang/gender filters."""
        if not self.piper_manager:
            return
        lang_map = {"Español": "es", "Inglés": "en", "Todos": None}
        gender_map = {"Masculino": "male", "Femenino": "female", "Todos": None}
        lang = lang_map.get(self.piper_lang_var.get())
        gender = gender_map.get(self.piper_gender_var.get())
        self.piper_manager.update_filters(language=lang, gender=gender)
        names = self.piper_manager.get_voice_names()
        self.piper_voice_dropdown.configure(values=names)
        if names:
            self.piper_voice_var.set(names[0])
            self._on_piper_voice_selected(names[0])

    def _on_piper_voice_selected(self, name: str = ""):
        """Update download button state based on whether model is local."""
        if not self.piper_manager or not name:
            return
        if self.piper_manager.is_downloaded(name):
            self.piper_dl_btn.configure(text="✔ Descargado", fg_color="#2E7D32", state=tk.DISABLED)
            self.piper_status_lbl.configure(text="Modelo disponible offline")
        else:
            self.piper_dl_btn.configure(text="Descargar modelo", fg_color="#E65100", state=tk.NORMAL)
            self.piper_status_lbl.configure(text="Modelo no descargado — requiere internet una vez")

    def _download_piper_model(self):
        """Download selected Piper model in background thread."""
        voice_name = self.piper_voice_var.get()
        if not voice_name or not self.piper_manager:
            return

        self.piper_dl_btn.configure(state=tk.DISABLED, text="Descargando...")
        self.piper_dl_bar.set(0)
        self.piper_dl_bar.grid()

        def _progress(downloaded, total, filename):
            if total > 0:
                self.after(0, lambda d=downloaded, t=total, f=filename: (
                    self.piper_dl_bar.set(d / t),
                    self.piper_status_lbl.configure(
                        text=f"Descargando {f}... {d // 1024}KB / {t // 1024}KB"
                    )
                ))

        def _run():
            try:
                self.piper_manager.download_voice(voice_name, progress_callback=_progress)
                self.after(0, lambda: (
                    self.piper_dl_bar.set(1),
                    self.piper_dl_bar.grid_remove(),
                    self._on_piper_voice_selected(voice_name),
                    self.piper_status_lbl.configure(text="Descarga completada. Listo para usar offline.")
                ))
            except Exception as e:
                self.after(0, lambda err=str(e): (
                    self.piper_dl_bar.grid_remove(),
                    self.piper_dl_btn.configure(state=tk.NORMAL, text="Reintentar", fg_color="#E65100"),
                    self.piper_status_lbl.configure(text=f"Error: {err}")
                ))

        threading.Thread(target=_run, daemon=True).start()


    
    def open_github(self):
        import webbrowser
        webbrowser.open("https://github.com/HectorZL")
    
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
    
    def load_file_chapters(self):
        """Extract chapters and their character counts in a background thread"""
        if not self.input_file:
            return
            
        self.chapter_toggle_btn.configure(state=tk.DISABLED, text="Cargando capítulos...")
        
        # Clear existing checkboxes in the scroll frame
        for child in self.chapter_scroll_frame.winfo_children():
            child.destroy()
            
        def _bg_load():
            try:
                import asyncio
                extractor = get_extractor(self.input_file)
                if not extractor:
                    self.after(0, lambda: self.chapter_toggle_btn.configure(text="Formato no soportado"))
                    return
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                content = loop.run_until_complete(extractor.extract_text(self.input_file))
                loop.close()
                
                # Format chapters list with character counts
                chapters_data = []
                if isinstance(content, list):
                    for i, chap in enumerate(content):
                        title = chap.get('title', f"Capítulo {i+1}") if isinstance(chap, dict) else str(chap)
                        text = chap.get('content', '') if isinstance(chap, dict) else str(chap)
                        chapters_data.append({
                            'index': i,
                            'title': title,
                            'chars': len(text)
                        })
                else:
                    # PDF or plain text
                    loop2 = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop2)
                    titles = loop2.run_until_complete(extractor.get_chapters(self.input_file))
                    loop2.close()
                    for i, title in enumerate(titles):
                        loop3 = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop3)
                        chap_text = loop3.run_until_complete(extractor.extract_chapter(self.input_file, i))
                        loop3.close()
                        chapters_data.append({
                            'index': i,
                            'title': title,
                            'chars': len(chap_text) if chap_text else 0
                        })
                
                self.after(0, lambda data=chapters_data: self._on_chapters_loaded(data))
            except Exception as e:
                print(f"Error loading chapters: {e}")
                self.after(0, lambda: self.chapter_toggle_btn.configure(text="Error al cargar capítulos"))

        threading.Thread(target=_bg_load, daemon=True).start()

    def _on_chapters_loaded(self, chapters_data):
        """Populate the chapter container inside the main window"""
        self.chapters_data = chapters_data
        
        self.chapter_checkboxes = []
        self.chapter_vars = []
        
        for ch in chapters_data:
            var = tk.BooleanVar(value=True)
            self.chapter_vars.append(var)
            
            # Format text: "Cap. X: Title (1,234 chars)"
            title_truncated = ch['title'][:50] + "..." if len(ch['title']) > 50 else ch['title']
            display_text = f"Cap. {ch['index']+1}: {title_truncated} ({ch['chars']:,} caract.)"
            
            cb = ctk.CTkCheckBox(
                self.chapter_scroll_frame,
                text=display_text,
                variable=var,
                command=self._on_chapter_selection_changed
            )
            cb.pack(anchor="w", pady=3, padx=5)
            self.chapter_checkboxes.append(cb)
            
        # Enable toggle button and update text
        self.selected_chapters = list(range(len(chapters_data)))
        self.chapter_toggle_btn.configure(state=tk.NORMAL)
        self._update_chapter_toggle_btn_text()

    def _on_chapter_selection_changed(self):
        """Called when a checkbox is toggled"""
        selected = []
        for i, var in enumerate(self.chapter_vars):
            if var.get():
                selected.append(i)
                
        if len(selected) == len(self.chapters_data):
            self.selected_chapters = list(range(len(self.chapters_data)))  # All selected
        elif len(selected) == 0:
            self.selected_chapters = []  # None selected
        else:
            self.selected_chapters = selected
            
        self._update_chapter_toggle_btn_text()

    def _update_chapter_toggle_btn_text(self):
        if not hasattr(self, 'chapters_data') or not self.chapters_data:
            self.chapter_toggle_btn.configure(text="📖 Seleccionar Capítulos (No hay archivo)")
            return
            
        total_chapters = len(self.chapters_data)
        selected_count = len(self.selected_chapters) if self.selected_chapters is not None else 0
        
        # Calculate selected characters
        if self.selected_chapters is not None:
            sel_chars = sum(self.chapters_data[i]['chars'] for i in self.selected_chapters)
        else:
            sel_chars = sum(ch['chars'] for ch in self.chapters_data)
            
        # Update text
        status_text = "▲ Ocultar" if self.chapter_container.winfo_viewable() else "▼ Mostrar"
        self.chapter_toggle_btn.configure(
            text=f"📖 {status_text} Capítulos — {selected_count}/{total_chapters} seleccionados ({sel_chars:,} caract.)"
        )

    def toggle_chapter_panel(self):
        """Toggle the visibility of the chapters list frame"""
        if self.chapter_container.winfo_viewable():
            self.chapter_container.grid_remove()
        else:
            self.chapter_container.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        self._update_chapter_toggle_btn_text()

    def _select_all_chapters(self):
        if not hasattr(self, 'chapter_vars'):
            return
        for var in self.chapter_vars:
            var.set(True)
        self.selected_chapters = list(range(len(self.chapters_data)))
        self._update_chapter_toggle_btn_text()
        
    def _deselect_all_chapters(self):
        if not hasattr(self, 'chapter_vars'):
            return
        for var in self.chapter_vars:
            var.set(False)
        self.selected_chapters = []
        self._update_chapter_toggle_btn_text()
    
    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """Format a byte count for display in the completion message."""
        size = float(size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def _get_output_format(self) -> str:
        """Return the normalized extension selected in the output format combo."""
        format_map = {
            "MP3 — comprimido (~0.5–1.5 MB/min)": "mp3",
            "WAV — sin pérdida (~2.5–3 MB/min)": "wav",
            "FLAC — sin pérdida (~0.8–2 MB/min)": "flac",
        }
        return format_map.get(self.output_format_var.get(), "mp3")

    def _on_output_format_changed(self, value=None):
        """Keep the suggested output filename and action button in sync."""
        output_format = self._get_output_format()
        if self.output_file:
            base, _ = os.path.splitext(self.output_file)
            self.output_file = f"{base}.{output_format}"
        self.convert_btn.configure(text=f"🚀 Convertir a {output_format.upper()}")

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
            
            # Load chapters and populate collapsible panel
            self.selected_chapters = None
            self.chapter_container.grid_remove()
            self.load_file_chapters()
            
            # Set default output filename
            output_format = self._get_output_format()
            output_name = f"{Path(filename).stem}.{output_format}"
            self.output_file = str(Path(filename).parent / output_name)
    
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

        output_format = self._get_output_format()
        if self.engine_mode.get() == "online" and output_format != "mp3":
            messagebox.showerror(
                "Formato no disponible",
                "El motor Online solo exporta MP3. Cambia a un motor Offline "
                "para usar WAV o FLAC."
            )
            return

        # Pick correct voice depending on mode
        if self.engine_mode.get() == "offline":
            selected_voice = self.piper_voice_var.get()
            if not selected_voice:
                messagebox.showerror("Error", "Por favor seleccione una voz Piper")
                return
            if self.piper_manager and not self.piper_manager.is_downloaded(selected_voice):
                messagebox.showerror(
                    "Modelo no descargado",
                    f"Descarga primero el modelo:\n{selected_voice}"
                )
                return
        elif self.engine_mode.get() == "chatterbox":
            if not self.chatterbox_manager or not self.chatterbox_manager.is_available():
                messagebox.showerror("Componentes faltantes", "Instale primero los componentes de IA local desde el panel de Chatterbox.")
                return
            
            voice_mode = self.cb_voice_mode_var.get()
            if voice_mode == "Voz Predeterminada":
                selected_voice = "default"
            else:
                selected_voice = self.cb_ref_audio_entry.get().strip()
                if not selected_voice or not os.path.exists(selected_voice):
                    messagebox.showerror("Error", "Por favor seleccione un archivo de audio de referencia válido.")
                    return
        elif self.engine_mode.get() == "kokoro":
            if not self.kokoro_manager or not self.kokoro_manager.is_available():
                messagebox.showerror("Componentes faltantes", "Instale primero la librería kokoro-onnx.")
                return
            if not self.kokoro_manager.is_downloaded():
                messagebox.showerror("Modelo no descargado", "Descarga primero el modelo de Kokoro desde su panel.")
                return
            selected_voice = self.kokoro_voice_var.get()
            if not selected_voice:
                messagebox.showerror("Error", "Por favor seleccione una voz de Kokoro.")
                return
        else:
            selected_voice = self.voice_var.get()
            if not selected_voice:
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
            self.output_format_dropdown.configure(state=tk.DISABLED)
            self.voice_dropdown.configure(state=tk.DISABLED)
            self.lang_dropdown.configure(state=tk.DISABLED)
            self.gender_dropdown.configure(state=tk.DISABLED)
            self.chapter_toggle_btn.configure(state=tk.DISABLED)
            self.cancel_btn.configure(state=tk.NORMAL)  # Enable cancel button during processing
            if hasattr(self, 'join_checkbox'):
                self.join_checkbox.configure(state=tk.DISABLED)
            if hasattr(self, 'keep_checkbox'):
                self.keep_checkbox.configure(state=tk.DISABLED)
        else:
            self.convert_btn.configure(state=tk.NORMAL)
            self.browse_btn.configure(state=tk.NORMAL)
            self.output_format_dropdown.configure(state="readonly")
            self.voice_dropdown.configure(state="readonly")
            self.lang_dropdown.configure(state="readonly")
            self.gender_dropdown.configure(state="readonly")
            self.chapter_toggle_btn.configure(state=tk.NORMAL if self.input_file else tk.DISABLED)
            self.cancel_btn.configure(state=tk.NORMAL)  # Keep cancel button enabled by default
            if hasattr(self, 'join_checkbox'):
                self.join_checkbox.configure(state=tk.NORMAL)
            if hasattr(self, 'keep_checkbox'):
                if self.join_chapters_var.get():
                    self.keep_checkbox.configure(state=tk.NORMAL)
                else:
                    self.keep_checkbox.configure(state=tk.DISABLED)
    
    def run_conversion(self):
        """Run the conversion process in a background thread"""
        try:
            if not self.input_file or not self.output_file:
                return

            # Get the selected voice (depends on engine mode)
            if self.engine_mode.get() == "offline":
                voice_name = self.piper_voice_var.get()
            elif self.engine_mode.get() == "chatterbox":
                voice_mode = self.cb_voice_mode_var.get()
                if voice_mode == "Voz Predeterminada":
                    voice_name = "default"
                else:
                    voice_name = self.cb_ref_audio_entry.get().strip()
            elif self.engine_mode.get() == "kokoro":
                voice_name = self.kokoro_voice_var.get()
            else:
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
            output_format = self._get_output_format()
            self.output_files_created = []
            if hasattr(self, 'selected_chapters') and self.selected_chapters:
                chap_numbers = [idx + 1 for idx in self.selected_chapters]
                min_chap = min(chap_numbers)
                max_chap = max(chap_numbers)
                suffix = f"_{min_chap}_{max_chap}" if min_chap != max_chap else f"_{min_chap}"
                base, ext = os.path.splitext(output_file)
                output_file = f"{base}{suffix}{ext}"

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
                    output_format=output_format,
                    progress_callback=lambda current, total, chars=0, total_chars=total_chars: 
                        self.progress_callback(
                            current/total if total > 0 else 0, 
                            1, 
                            int((current/total) * total_chars) if total > 0 else 0, 
                            total_chars,
                            1
                        )
                )
                self.output_files_created = [output_file]
            elif isinstance(content, list) and content:
                # Chapter-based conversion - process each chapter separately
                # Filter chapters if selection exists
                if hasattr(self, 'selected_chapters') and self.selected_chapters is not None:
                    content = [content[i] for i in self.selected_chapters 
                             if 0 <= i < len(content)]
                    self.total_chapters = len(content)
                    total_chars = sum(
                        len(chapter.get('content', '') if isinstance(chapter, dict) else str(chapter))
                        for chapter in content
                    )
                    self.after(0, lambda: self.update_progress_ui(total_chapters=self.total_chapters, total_chars=total_chars))
                
                self.current_chapter = 0
                
                # Convert each chapter
                chapter_files = []
                for i, chapter in enumerate(content):
                    self.current_chapter = i + 1
                    
                    # Get chapter content and character count
                    chapter_content = chapter.get('content', '') if isinstance(chapter, dict) else str(chapter)
                    
                    # Skip empty chapters to prevent ValueError crashes
                    if not chapter_content or not chapter_content.strip():
                        print(f"Saltando capítulo vacío {i+1}: {chapter.get('title', 'Sin título') if isinstance(chapter, dict) else 'Capítulo ' + str(i+1)}")
                        processed_before = sum(
                            len(c.get('content', '') if isinstance(c, dict) else str(c))
                            for c in content[:i]
                        )
                        self.after(0, lambda i=i, total=len(content), current_chars=processed_before: 
                            self.progress_callback(
                                i + 1, 
                                total,
                                current_chars,
                                total_chars,
                                i + 1
                            )
                        )
                        continue
                        
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
                        output_format=output_format,
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
                    chapter_files.append(chapter_output)
                
                # Merge chapters if requested
                if self.join_chapters_var.get() and chapter_files:
                    self.after(0, lambda: self.status_var.set("Uniendo capítulos..."))
                    self.audio_converter._combine_audio_files(chapter_files, output_file)
                    
                    if not self.keep_chapters_var.get():
                        for f in chapter_files:
                            try:
                                if os.path.exists(f):
                                    os.remove(f)
                            except Exception as e:
                                print(f"Error al borrar archivo individual {f}: {e}")

                self.output_files_created = [output_file] if self.join_chapters_var.get() and chapter_files else chapter_files
                    
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
                # Update progress bar based on characters if available, otherwise use chapter progress
                if total_chars > 0 and current_chars > 0:
                    progress = current_chars / total_chars
                    self.progress_bar.set(progress)
                    
                    # Update character information
                    self.processed_characters = current_chars
                    self.total_characters = total_chars
                    percent = (current_chars / total_chars * 100) if total_chars > 0 else 0
                    self.char_label.configure(
                        text=f"Caracteres: {current_chars:,}/{total_chars:,} ({percent:.1f}%)"
                    )
                    
                    # Update chapter information based on character progress
                    if hasattr(self, 'total_chapters') and self.total_chapters > 0:
                        # Calculate current chapter based on character progress
                        if total > 0:
                            chapter_progress = current / total
                            current_chapter = min(self.total_chapters, max(1, int(chapter_progress * self.total_chapters) + 1))
                            self.current_chapter = current_chapter
                            self.chapter_label.configure(text=f"Capítulo: {self.current_chapter}/{self.total_chapters}")
                
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
        """Handle successful conversion and report the generated file size."""
        self.progress_bar.set(1.0)
        generated_files = [
            path for path in self.output_files_created
            if path and os.path.exists(path)
        ]
        total_size = sum(os.path.getsize(path) for path in generated_files)
        if generated_files:
            size_text = self._format_file_size(total_size)
            count_text = "archivo" if len(generated_files) == 1 else "archivos"
            detail = f"\nTamaño total: {size_text} ({len(generated_files)} {count_text})"
            self.status_var.set(f"¡Conversión completada! Tamaño: {size_text}")
        else:
            detail = ""
            self.status_var.set("¡Conversión completada con éxito!")

        messagebox.showinfo(
            "Éxito",
            f"La conversión se ha completado correctamente.{detail}"
        )
        # Reset the UI after a short delay to show the success message
        self.after(2000, self.reset_ui_state)
    
    def on_conversion_error(self, error_msg: str):
        """Handle conversion errors"""
        self.status_var.set("Error en la conversión")
        messagebox.showerror("Error", 
            f"Ocurrió un error durante la conversión:\n{error_msg}")
        self.progress_bar.set(0)

    # ─── Kokoro panel helpers ──────────────────────────────────────────────────

    def _check_kokoro_status(self):
        """Verifica si Kokoro está listo (librerías instaladas y modelos descargados)."""
        if not self.kokoro_manager:
            return

        if not self.kokoro_manager.is_available():
            self.kokoro_status_lbl.configure(
                text="Falta instalar dependencias de Kokoro (kokoro-onnx)",
                text_color="#F44336"
            )
            self.kokoro_dl_btn.configure(state=tk.DISABLED)
            self.kokoro_voice_dropdown.configure(state=tk.DISABLED)
            return

        if self.kokoro_manager.is_downloaded():
            import onnxruntime as ort
            providers = ort.get_available_providers()
            device_str = "GPU (CUDA)" if "CUDAExecutionProvider" in providers else "CPU"
            self.kokoro_status_lbl.configure(
                text=f"Modelo Kokoro listo para usar offline. Dispositivo de IA: {device_str}",
                text_color="#4CAF50"
            )
            self.kokoro_dl_btn.grid_remove()
            self.kokoro_voice_dropdown.configure(state="readonly")
        else:
            self.kokoro_status_lbl.configure(
                text="Componentes listos. Requiere descargar modelo (180MB)",
                text_color="#FF9800"
            )
            self.kokoro_dl_btn.grid()
            self.kokoro_dl_btn.configure(state=tk.NORMAL)
            self.kokoro_voice_dropdown.configure(state=tk.DISABLED)

    def _update_kokoro_voices(self, event=None):
        """Actualiza el desplegable de voces de Kokoro según el idioma seleccionado."""
        if not self.kokoro_manager:
            return
        lang_map = {"Español": "es", "Inglés": "en"}
        lang = lang_map.get(self.kokoro_lang_var.get())
        self.kokoro_manager.update_filters(language=lang)
        names = self.kokoro_manager.get_voice_names()
        self.kokoro_voice_dropdown.configure(values=names)
        if names:
            self.kokoro_voice_var.set(names[0])

    def _download_kokoro_model(self):
        """Descarga el modelo ONNX y voices bin en segundo plano."""
        self.kokoro_dl_btn.configure(state=tk.DISABLED)
        self.kokoro_dl_bar.grid()
        self.kokoro_dl_bar.set(0)

        def progress_cb(downloaded, total, filename):
            percentage = downloaded / total
            def update_ui():
                self.kokoro_dl_bar.set(percentage)
                self.kokoro_status_lbl.configure(
                    text=f"Descargando {filename}... {percentage*100:.1f}%"
                )
            self.after(0, update_ui)

        def run_dl():
            try:
                self.kokoro_manager.download_model(progress_callback=progress_cb)
                def success_ui():
                    self.kokoro_dl_bar.grid_remove()
                    self._check_kokoro_status()
                    self._update_kokoro_voices()
                    messagebox.showinfo("Descarga Exitosa", "El modelo y las voces de Kokoro se han descargado correctamente.")
                self.after(0, success_ui)
            except Exception as e:
                def error_ui():
                    self.kokoro_dl_bar.grid_remove()
                    self.kokoro_dl_btn.configure(state=tk.NORMAL)
                    self._check_kokoro_status()
                    messagebox.showerror("Error", f"Fallo al descargar el modelo de Kokoro: {e}")
                self.after(0, error_ui)

        threading.Thread(target=run_dl, daemon=True).start()
