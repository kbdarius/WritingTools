import os
import shutil
import subprocess
import sys
from pathlib import Path
from version import APP_DISPLAY_NAME


def run_pyinstaller_build():
    pyinstaller_arguments = [
        "--onefile",
        "--windowed",
        "--icon=icons/app_icon.ico",
        f"--name={APP_DISPLAY_NAME}",
        "--clean",
        "--noconfirm",
        # Exclude unnecessary modules
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        "--exclude-module", "IPython",
        "--exclude-module", "jedi",
        "--exclude-module", "email_validator",
        # NOTE: do NOT exclude `cryptography` — google-genai's auth chain pulls
        # it in heavily during `genai.Client()` construction. Excluding it
        # makes the compiled exe crash on startup.
        "--exclude-module", "psutil",
        "--exclude-module", "pyzmq",
        "--exclude-module", "tornado",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        "--additional-hooks-dir", "hooks",
        # Exclude modules related to PySide6 that are not used
        "--exclude-module", "PySide6.QtNetwork",
        "--exclude-module", "PySide6.QtXml",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQuickWidgets",
        "--exclude-module", "PySide6.QtPrintSupport",
        "--exclude-module", "PySide6.QtSql",
        "--exclude-module", "PySide6.QtTest",
        "--exclude-module", "PySide6.QtSvg",
        "--exclude-module", "PySide6.QtSvgWidgets",
        "--exclude-module", "PySide6.QtHelp",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtMultimediaWidgets",
        "--exclude-module", "PySide6.QtOpenGL",
        "--exclude-module", "PySide6.QtOpenGLWidgets",
        "--exclude-module", "PySide6.QtPositioning",
        "--exclude-module", "PySide6.QtLocation",
        "--exclude-module", "PySide6.QtSerialPort",
        "--exclude-module", "PySide6.QtWebChannel",
        "--exclude-module", "PySide6.QtWebSockets",
        "--exclude-module", "PySide6.QtWinExtras",
        "--exclude-module", "PySide6.QtNetworkAuth",
        "--exclude-module", "PySide6.QtRemoteObjects",
        "--exclude-module", "PySide6.QtTextToSpeech",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebEngine",
        "--exclude-module", "PySide6.QtBluetooth",
        "--exclude-module", "PySide6.QtNfc",
        "--exclude-module", "PySide6.QtWebView",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtPdf",
        "--exclude-module", "PySide6.QtPdfWidgets",
        "--exclude-module", "PySide6.QtQuick3D",
        "--exclude-module", "PySide6.QtQuickControls2",
        "--exclude-module", "PySide6.QtQuickParticles",
        "--exclude-module", "PySide6.QtQuickTest",
        "--exclude-module", "PySide6.QtQuickWidgets",
        "--exclude-module", "PySide6.QtSensors",
        "--exclude-module", "PySide6.QtStateMachine",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.Qt3DRender",
        "--exclude-module", "PySide6.Qt3DInput",
        "--exclude-module", "PySide6.Qt3DLogic",
        "--exclude-module", "PySide6.Qt3DAnimation",
        "--exclude-module", "PySide6.Qt3DExtras",
        # Local Read Aloud is imported lazily, so collect its runtime and the
        # native eSpeak/ONNX files explicitly.
        "--hidden-import", "kokoro_onnx",
        "--hidden-import", "piper",
        "--hidden-import", "pythoncom",
        "--hidden-import", "pywintypes",
        "--hidden-import", "win32com.client",
        "--collect-all", "espeakng_loader",
        # Kokoro's phonemizer imports csvw/language-tags at runtime. The
        # package's JSON registry is data (not Python), so PyInstaller will
        # otherwise omit it and Read Aloud fails on the first click.
        "--collect-data", "language_tags",
        "main.py"
    ]

    # Conda-based Python environments keep several standard-library runtime
    # DLLs outside Python's DLLs directory. PyInstaller cannot always discover
    # them automatically, so explicitly bundle them when they are present.
    runtime_bin = Path(sys.prefix) / "Library" / "bin"
    for dll_name in (
        "ffi.dll", "libbz2.dll", "libcrypto-3-x64.dll", "libexpat.dll",
        "liblzma.dll", "libssl-3-x64.dll", "sqlite3.dll",
    ):
        dll_path = runtime_bin / dll_name
        if dll_path.exists():
            pyinstaller_arguments.extend(["--add-binary", f"{dll_path};."])

    # Piper's Farsi phonemizer needs its voice tables, but not the package's
    # training tools, web templates, Arabic diacritizer model, or image assets.
    piper_espeak_data = (
        Path(sys.prefix) / "Lib" / "site-packages" / "piper" / "espeak-ng-data"
    )
    if piper_espeak_data.exists():
        pyinstaller_arguments.extend([
            "--add-data", f"{piper_espeak_data};piper/espeak-ng-data"
        ])

    kokoro_config = (
        Path(sys.prefix) / "Lib" / "site-packages" / "kokoro_onnx" / "config.json"
    )
    if kokoro_config.exists():
        pyinstaller_arguments.extend([
            "--add-data", f"{kokoro_config};kokoro_onnx"
        ])

    try:
        # Remove previous build directories
        for build_artifact in ('dist', 'build', '__pycache__'):
            if os.path.exists(build_artifact):
                shutil.rmtree(build_artifact)

        # Run PyInstaller
        # Using the active interpreter avoids accidentally picking up a
        # globally installed PyInstaller from another Python environment.
        subprocess.run([sys.executable, "-m", "PyInstaller", *pyinstaller_arguments], check=True)
        print("Build completed successfully!")

        # Clean up unnecessary files
        for build_artifact in ('build', '__pycache__'):
            if os.path.exists(build_artifact):
                shutil.rmtree(build_artifact)

        # No need to copy data files manually since they are included
        # in the executable using --add-data

    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_pyinstaller_build()
