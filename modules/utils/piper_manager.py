"""
Gestor de voces Piper TTS (offline).
Maneja la descarga, caché y uso de modelos .onnx de Piper.
"""
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import List, Dict, Optional, Callable

# Directorio local donde se guardan los modelos Piper
MODELS_DIR = Path(__file__).parent.parent.parent / "piper_models"

# Catálogo de voces en español/inglés disponibles en Piper
# Formato: {nombre_display: {model_url, config_url, lang, gender, quality}}
PIPER_VOICE_CATALOG: Dict[str, Dict] = {
    # ── Español (México) ─────────────────────────────────────────────────────
    "Piper · MX · Claude (Femenino, High)": {
        "model":  "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/claude/high/es_MX-claude-high.onnx",
        "config": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/claude/high/es_MX-claude-high.onnx.json",
        "lang": "es", "gender": "female", "quality": "high",
    },
    # ── Inglés ───────────────────────────────────────────────────────────────
    "Piper · EN · Lessac (Femenino, High)": {
        "model":  "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx",
        "config": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx.json",
        "lang": "en", "gender": "female", "quality": "high",
    },
}


class PiperVoiceManager:
    """Gestiona la descarga y uso de voces Piper TTS."""

    def __init__(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self._catalog = PIPER_VOICE_CATALOG
        self._filtered: List[str] = list(self._catalog.keys())

    # ─── Filtros ──────────────────────────────────────────────────────────────

    def update_filters(self, language: Optional[str] = None, gender: Optional[str] = None):
        """Filtra el catálogo por idioma y/o género."""
        result = []
        for name, info in self._catalog.items():
            if language and info["lang"] != language:
                continue
            if gender and info["gender"].lower() != gender.lower():
                continue
            result.append(name)
        self._filtered = result

    def get_voice_names(self) -> List[str]:
        return list(self._filtered)

    def get_all_names(self) -> List[str]:
        return list(self._catalog.keys())

    def is_downloaded(self, voice_name: str) -> bool:
        info = self._catalog.get(voice_name)
        if not info:
            return False
        model_path = self._model_path(voice_name)
        config_path = self._config_path(voice_name)
        return model_path.exists() and config_path.exists()

    # ─── Rutas locales ────────────────────────────────────────────────────────

    def _safe_name(self, voice_name: str) -> str:
        return voice_name.replace(" ", "_").replace("·", "").replace("(", "").replace(")", "").replace(",", "").strip("_")

    def _model_path(self, voice_name: str) -> Path:
        safe_name = f"{self._safe_name(voice_name)}.onnx"
        
        # Primero buscar si el modelo viene empaquetado en el .exe (PyInstaller root)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundled_path = Path(sys._MEIPASS) / "piper_models" / safe_name
            if bundled_path.exists():
                return bundled_path
                
        # Fallback a la carpeta local externa
        return MODELS_DIR / safe_name

    def _config_path(self, voice_name: str) -> Path:
        safe_name = f"{self._safe_name(voice_name)}.onnx.json"
        
        # Buscar en el paquete
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundled_path = Path(sys._MEIPASS) / "piper_models" / safe_name
            if bundled_path.exists():
                return bundled_path
                
        # Fallback a la carpeta local externa
        return MODELS_DIR / safe_name

    # ─── Descarga ─────────────────────────────────────────────────────────────

    def download_voice(
        self,
        voice_name: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> bool:
        """
        Descarga el modelo .onnx y su .json de configuración.
        progress_callback(bytes_downloaded, bytes_total, filename)
        Retorna True si exitoso.
        """
        info = self._catalog.get(voice_name)
        if not info:
            raise ValueError(f"Voz desconocida: {voice_name}")

        urls = [
            (info["model"],  self._model_path(voice_name)),
            (info["config"], self._config_path(voice_name)),
        ]

        for url, dest in urls:
            if dest.exists():
                continue
            try:
                def _reporthook(count, block_size, total_size):
                    if progress_callback:
                        downloaded = count * block_size
                        progress_callback(min(downloaded, total_size), total_size, dest.name)

                urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
            except Exception as e:
                if dest.exists():
                    dest.unlink()
                raise Exception(f"Error descargando {dest.name}: {e}")

        return True

    # ─── Síntesis ─────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        voice_name: str,
        output_wav: str,
    ):
        """
        Genera audio WAV desde texto usando Piper offline.
        Requiere que el modelo esté descargado.
        """
        if not self.is_downloaded(voice_name):
            raise FileNotFoundError(
                f"Modelo no descargado: '{voice_name}'. "
                "Descárgalo primero desde la sección Piper."
            )

        model_path = self._model_path(voice_name)
        config_path = self._config_path(voice_name)

        try:
            from piper import PiperVoice  # type: ignore
            from piper.config import PiperConfig
            import onnxruntime
            import json

            # Cargar config
            with open(config_path, "r", encoding="utf-8") as f:
                config_dict = json.load(f)

            # Optimización inteligente: Usar exactamente la mitad de los núcleos del procesador
            # (Garantiza buen rendimiento sin congelar ni asfixiar cualquier PC donde se ejecute)
            import os
            cpu_count = os.cpu_count() or 4
            optimal_threads = max(1, cpu_count // 2)

            sess_opts = onnxruntime.SessionOptions()
            sess_opts.intra_op_num_threads = optimal_threads
            sess_opts.inter_op_num_threads = 1
            
            # Optimización de RAM: Forzar al motor a no acaparar memoria en caché.
            # (Extremadamente útil para que el sistema mantenga su RAM libre en todo momento)
            sess_opts.enable_cpu_mem_arena = False
            sess_opts.enable_mem_pattern = False

            session = onnxruntime.InferenceSession(
                str(model_path),
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"]
            )

            kwargs = {
                "config": PiperConfig.from_dict(config_dict),
                "session": session,
                "download_dir": Path.cwd()
            }

            # Configurar para que espeak no de problemas al estar empaquetado en Windows
            import sys
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                espeak_data = Path(sys._MEIPASS) / "piper" / "espeak-ng-data"
                if espeak_data.exists():
                    kwargs["espeak_data_dir"] = espeak_data

            voice = PiperVoice(**kwargs)

            from piper.config import SynthesisConfig
            
            # Inyección acústica: ralentización del tempo y micro-silencios
            # Para Python wrapper, usamos SynthesisConfig
            syn_config = SynthesisConfig(length_scale=1.15)
            
            import wave
            with wave.open(output_wav, "wb") as wav_file:
                voice.synthesize_wav(
                    text, 
                    wav_file, 
                    syn_config=syn_config
                )
                # --- INYECCIÓN DE RESPIRACIÓN (Digital Silence) ---
                # Leemos los parámetros configurados por Piper
                try:
                    channels = wav_file.getnchannels()
                    sampwidth = wav_file.getsampwidth()
                    framerate = wav_file.getframerate()
                    # Si Piper inicializó correctamente el stream, calculamos e inyectamos 0.5s de silencio
                    if channels > 0 and sampwidth > 0 and framerate > 0:
                        pausa_segundos = 0.5
                        num_frames = int(framerate * pausa_segundos)
                        silence_bytes = b'\x00' * (num_frames * channels * sampwidth)
                        wav_file.writeframes(silence_bytes)
                except Exception as silence_e:
                    print(f"Nota: No se pudo inyectar pausa al final del WAV: {silence_e}")
                    
        except Exception as e:
            raise Exception(f"Error en síntesis Piper: {e}")

    def wav_to_mp3(self, wav_path: str, mp3_path: str):
        """Convierte WAV a MP3 súper ligero usando compresión nativa y eficiente."""
        try:
            import soundfile as sf
            data, samplerate = sf.read(wav_path)
            
            # Comprimir el audio nativamente como MP3 en máxima eficiencia (Layer III) sin ffmpeg
            sf.write(mp3_path, data, samplerate, format='MP3', subtype='MPEG_LAYER_III')
        except Exception as e:
            print(f"Aviso: Fallo escritura mp3 nativa con soundfile: {e}")
            import subprocess, shutil
            if shutil.which("ffmpeg"):
                try:
                    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", mp3_path], check=True, capture_output=True)
                except:
                    shutil.copy2(wav_path, mp3_path)
            else:
                shutil.copy2(wav_path, mp3_path)
