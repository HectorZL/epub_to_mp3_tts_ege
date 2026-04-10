"""
Build script para EpubToMP3 TTS
Genera un ejecutable único en la carpeta dist/
"""
import subprocess
import sys
import shutil
from pathlib import Path

APP_NAME = "EpubToMP3"
ENTRY_POINT = "main.py"
ICON_PATH = None          # Pon aquí la ruta a un .ico si tienes uno, e.g. "assets/icon.ico"

def build():
    root = Path(__file__).parent

    # Limpiar builds anteriores
    for folder in ["build", "dist", "__pycache__"]:
        target = root / folder
        if target.exists():
            shutil.rmtree(target)
            print(f"[limpieza] eliminado: {folder}/")

    # Construir el comando de PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",            # Ejecutable único
        "--windowed",           # Sin consola (GUI)
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
    ]

    if ICON_PATH and Path(ICON_PATH).exists():
        cmd += ["--icon", ICON_PATH]

    # Incluir módulos ocultos (edge-tts usa asyncio + aiohttp internamente)
    hidden_imports = [
        "edge_tts",
        "aiohttp",
        "ebooklib",
        "ebooklib.epub",
        "PyPDF2",
        "customtkinter",
        "lxml",
        "lxml.etree",
        "lxml.html",
        "bs4",
        "pkg_resources.py2_compat",
    ]
    for mod in hidden_imports:
        cmd += ["--hidden-import", mod]

    # Incluir datos de customtkinter (temas/assets)
    try:
        import customtkinter
        ctk_path = Path(customtkinter.__file__).parent
        cmd += ["--add-data", f"{ctk_path};customtkinter/"]
    except ImportError:
        print("[aviso] customtkinter no encontrado para incluir assets")

    # Incluir datos requeridos por Piper (espeak-ng-data)
    try:
        import piper
        piper_path = Path(piper.__file__).parent
        cmd += ["--add-data", f"{piper_path};piper/"]
    except ImportError:
        pass

    # Incluir modelos de voces Piper que ya estén descargados
    piper_models_dir = root / "piper_models"
    if piper_models_dir.exists() and any(piper_models_dir.iterdir()):

        cmd += ["--add-data", f"{piper_models_dir};piper_models/"]
        archivos = len(list(piper_models_dir.iterdir()))
        print(f"\n[aviso] Se empacaran {archivos} archivos de piper_models dentro del EXE.")
        print("[aviso] Esto hara que el ejecutable sea mas pesado, pero funcionara 100% offline sin descargas previas.")
        print()


    cmd.append(ENTRY_POINT)

    print("\n[build] Ejecutando PyInstaller...")
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode == 0:
        exe = root / "dist" / f"{APP_NAME}.exe"
        print(f"\n[OK] Compilacion exitosa: {exe}")
    else:
        print("\n[ERROR] La compilacion fallo. Revisa los errores arriba.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
