"""
Gestor de Kokoro TTS (offline con ONNX).
Maneja la detección de dependencias, descarga de modelos, inicialización de kokoro-onnx y síntesis.
"""
import os
import sys
import urllib.request
from pathlib import Path
from typing import List, Dict, Optional, Callable
import soundfile as sf
import numpy as np

# Directorio local donde se guardan los modelos Kokoro
MODELS_DIR = Path(__file__).parent.parent.parent / "kokoro_models"

# Catálogo de voces de Kokoro v1.0
KOKORO_VOICES: Dict[str, Dict[str, str]] = {
    # ── Español ──────────────────────────────────────────────────────────────
    "Kokoro · ES · Dora (Femenino)": {
        "id": "ef_dora", "lang": "es", "gender": "female",
    },
    "Kokoro · ES · Alex (Masculino)": {
        "id": "em_alex", "lang": "es", "gender": "male",
    },
    "Kokoro · ES · Santa (Masculino)": {
        "id": "em_santa", "lang": "es", "gender": "male",
    },
    # ── Inglés ───────────────────────────────────────────────────────────────
    "Kokoro · EN · Sarah (Femenino)": {
        "id": "af_sarah", "lang": "en-us", "gender": "female",
    },
    "Kokoro · EN · Bella (Femenino)": {
        "id": "af_bella", "lang": "en-us", "gender": "female",
    },
    "Kokoro · EN · Nicole (Femenino)": {
        "id": "af_nicole", "lang": "en-us", "gender": "female",
    },
    "Kokoro · EN · Sky (Femenino)": {
        "id": "af_sky", "lang": "en-us", "gender": "female",
    },
    "Kokoro · EN · Michael (Masculino)": {
        "id": "am_michael", "lang": "en-us", "gender": "male",
    },
    "Kokoro · EN · Adam (Masculino)": {
        "id": "am_adam", "lang": "en-us", "gender": "male",
    },
    "Kokoro · EN · Fenrir (Masculino)": {
        "id": "am_fenrir", "lang": "en-us", "gender": "male",
    },
}

class KokoroVoiceManager:
    def __init__(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.kokoro = None
        self._catalog = KOKORO_VOICES
        self._filtered: List[str] = list(self._catalog.keys())
        
        # Enlaces de descarga oficiales para v1.0
        self.model_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx"
        self.voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
        
        self.model_path = MODELS_DIR / "kokoro-v1.0.fp16.onnx"
        self.voices_path = MODELS_DIR / "voices-v1.0.bin"

    def is_available(self) -> bool:
        """Verifica si las librerías necesarias están instaladas."""
        try:
            import kokoro_onnx
            import onnxruntime
            return True
        except ImportError:
            return False

    def is_downloaded(self) -> bool:
        """Verifica si el modelo y las voces están descargados."""
        return self.model_path.exists() and self.voices_path.exists()

    def get_voice_names(self) -> List[str]:
        return list(self._filtered)

    def get_all_names(self) -> List[str]:
        return list(self._catalog.keys())

    def update_filters(self, language: Optional[str] = None, gender: Optional[str] = None):
        """Filtra el catálogo por idioma y/o género."""
        result = []
        for name, info in self._catalog.items():
            if language:
                # Mapear idioma del filtro ('es', 'en') al lang del catálogo ('es', 'en-us')
                filter_lang = "es" if language == "es" else "en"
                item_lang = "es" if info["lang"] == "es" else "en"
                if filter_lang != item_lang:
                    continue
            if gender and info["gender"].lower() != gender.lower():
                continue
            result.append(name)
        self._filtered = result

    def download_model(self, progress_callback: Optional[Callable[[int, int, str], None]] = None) -> bool:
        """
        Descarga el modelo ONNX y su archivo de voces.
        progress_callback(bytes_downloaded, bytes_total, filename)
        """
        urls = [
            (self.model_url, self.model_path),
            (self.voices_url, self.voices_path)
        ]

        for url, dest in urls:
            if dest.exists():
                continue
            try:
                def _reporthook(count, block_size, total_size):
                    if progress_callback:
                        downloaded = count * block_size
                        progress_callback(min(downloaded, total_size), total_size, dest.name)

                print(f"Descargando {dest.name} desde {url}...")
                urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
            except Exception as e:
                if dest.exists():
                    dest.unlink()
                raise Exception(f"Error descargando {dest.name}: {e}")

        return True

    def _load_model(self):
        """Carga e inicializa el modelo Kokoro (Lazy Loading)."""
        if self.kokoro is not None:
            return

        if not self.is_available():
            raise ImportError(
                "La librería 'kokoro-onnx' o 'onnxruntime' no está instalada."
            )
            
        if not self.is_downloaded():
            raise FileNotFoundError(
                "El modelo de Kokoro no está descargado. Por favor, descárgalo desde la sección Kokoro."
            )

        # Precargar DLLs de CUDA/cuDNN desde PyTorch si están disponibles
        try:
            import torch
            torch_lib = Path(torch.__file__).parent / "lib"
            if torch_lib.exists():
                print(f"Pre-cargando DLLs de CUDA/cuDNN desde PyTorch: {torch_lib}")
                os.add_dll_directory(str(torch_lib))
                os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ["PATH"]
        except Exception as e:
            print(f"Advertencia al pre-cargar DLLs de PyTorch: {e}")

        from kokoro_onnx import Kokoro
        import onnxruntime as ort

        # Detección inteligente de aceleradores (CUDA en ONNX runtime)
        available_providers = ort.get_available_providers()
        print(f"Proveedores de ejecución ONNX disponibles: {available_providers}")
        
        # Preferir CUDA si está disponible, de lo contrario CPU
        if "CUDAExecutionProvider" in available_providers:
            os.environ["ONNX_PROVIDER"] = "CUDAExecutionProvider"
            print("Configurando ONNX_PROVIDER a CUDAExecutionProvider")
        else:
            os.environ["ONNX_PROVIDER"] = "CPUExecutionProvider"
            print("Configurando ONNX_PROVIDER a CPUExecutionProvider")

        # Cargar Kokoro
        self.kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        print("Modelo Kokoro cargado correctamente.")

    def synthesize(
        self,
        text: str,
        voice_name: str,
        output_wav: str,
        speed: float = 1.0
    ):
        """
        Sintetiza texto a audio WAV usando Kokoro.
        """
        self._load_model()
        
        # Obtener información de la voz del catálogo
        voice_info = self._catalog.get(voice_name)
        if not voice_info:
            # Fallback a primera voz si no coincide el nombre exacto
            voice_id = "ef_dora"
            lang = "es"
        else:
            voice_id = voice_info["id"]
            lang = voice_info["lang"]

        clean_text = text.strip()
        print(f"Sintetizando con Kokoro (Voz: {voice_id}, Lang: {lang}, Texto: {clean_text[:50]}...)")

        try:
            # Generar audio con kokoro-onnx (retorna numpy array y sample rate)
            samples, sample_rate = self.kokoro.create(
                text=clean_text,
                voice=voice_id,
                speed=speed,
                lang=lang
            )
            
            # --- INYECCIÓN DE SILENCIO / RESPIRACIÓN ---
            # Agrega 0.4 segundos de silencio al final de cada párrafo
            silence_duration = 0.4
            silence_samples = int(sample_rate * silence_duration)
            silence = np.zeros(silence_samples, dtype=samples.dtype)
            
            # Concatenar silencio final
            final_audio = np.concatenate([samples, silence])

            # Guardar como WAV
            sf.write(output_wav, final_audio, sample_rate)
            print(f"Audio guardado correctamente en: {output_wav}")

        except Exception as e:
            raise Exception(f"Error en la síntesis con Kokoro: {str(e)}")
