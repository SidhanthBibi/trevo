"""First-time setup wizard for trevo.

Run this once to:
1. Create a virtual environment
2. Install dependencies
3. Walk you through API key setup
4. Verify everything works
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"
VENV_DIR = ROOT / ".venv"


def _print_header(text: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def _print_step(n: int, text: str) -> None:
    print(f"\n  [{n}] {text}")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"      > {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


def step1_check_python():
    """Verify Python version."""
    _print_step(1, "Checking Python version...")
    v = sys.version_info
    print(f"      Python {v.major}.{v.minor}.{v.micro}")

    if v.major < 3 or (v.major == 3 and v.minor < 11):
        print("      [!] trevo requires Python 3.11+")
        print("      Download from: https://www.python.org/downloads/")
        sys.exit(1)

    if v.minor >= 14:
        print("      [!] Python 3.14 detected — some packages (torch, faster-whisper)")
        print("          may not have wheels yet. If installs fail, use Python 3.12.")
        print("          Download 3.12: https://www.python.org/downloads/release/python-3129/")
        resp = input("      Continue anyway? [y/N]: ").strip().lower()
        if resp != "y":
            sys.exit(0)

    print("      [OK]")


def step2_create_venv():
    """Create virtual environment."""
    _print_step(2, "Creating virtual environment...")

    if VENV_DIR.exists():
        print(f"      .venv already exists at {VENV_DIR}")
        resp = input("      Recreate it? [y/N]: ").strip().lower()
        if resp != "y":
            print("      [SKIP]")
            return

    _run([sys.executable, "-m", "venv", str(VENV_DIR)])
    print("      [OK] Virtual environment created")


def _get_pip() -> str:
    """Return path to pip inside the venv."""
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


def _get_python() -> str:
    """Return path to python inside the venv."""
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def step3_install_deps():
    """Install Python dependencies."""
    _print_step(3, "Installing dependencies (this takes a few minutes)...")

    pip = _get_pip()

    # Upgrade pip first
    _run([pip, "install", "--upgrade", "pip"], capture_output=True)

    # Install core deps first (most likely to succeed)
    core_deps = [
        "PyQt6>=6.6.0",
        "PyQt6-Frameless-Window>=0.4.0",
        "keyboard>=0.13.5",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "pyperclip>=1.8.2",
        "pyautogui>=0.9.54",
        "psutil>=5.9.0",
        "loguru>=0.7.0",
        "httpx>=0.27.0",
        "Pillow>=10.0.0",
    ]
    print("\n      Installing core packages...")
    result = _run([pip, "install"] + core_deps, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"      [!] Some core packages failed:\n{result.stderr[:500]}")
    else:
        print("      [OK] Core packages installed")

    # Install API client packages
    api_deps = ["deepgram-sdk>=4.5.0", "openai>=1.30.0", "anthropic>=0.25.0"]
    print("\n      Installing API client packages...")
    result = _run([pip, "install"] + api_deps, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"      [!] Some API packages failed: {result.stderr[:300]}")
    else:
        print("      [OK] API packages installed")

    # Install Windows-specific
    if sys.platform == "win32":
        print("\n      Installing Windows integration (pywin32)...")
        result = _run([pip, "install", "pywin32>=306"], capture_output=True, text=True)
        if result.returncode != 0:
            print("      [!] pywin32 failed — context detection will be limited")
        else:
            print("      [OK] pywin32 installed")

    # Install TOML parser
    print("\n      Installing config parser...")
    _run([pip, "install", "tomli>=2.0.0"], capture_output=True)
    print("      [OK]")

    # Try torch + faster-whisper (may fail on 3.14)
    print("\n      Installing offline STT (torch + faster-whisper)...")
    print("      (This is ~2GB download — skip if you only want cloud STT)")
    resp = input("      Install offline mode? [Y/n]: ").strip().lower()
    if resp != "n":
        result = _run(
            [pip, "install", "torch>=2.0.0", "faster-whisper>=1.0.0"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("      [!] torch/faster-whisper failed (likely Python 3.14 issue)")
            print("      Offline mode won't work, but cloud STT (Deepgram) will.")
        else:
            print("      [OK] Offline STT ready")
    else:
        print("      [SKIP] Offline mode skipped")

    # Install PyInstaller for building .exe
    print("\n      Installing PyInstaller (for building .exe)...")
    _run([pip, "install", "pyinstaller>=6.0"], capture_output=True)
    print("      [OK]")


def step4_setup_api_keys():
    """Walk user through API key configuration."""
    _print_step(4, "Setting up API keys...")

    print("""
      trevo supports several providers. We recommend the FREE options:

      RECOMMENDED (Free):
        A. Groq  — FREE STT + LLM (30 req/min)
           Sign up: https://console.groq.com
           Get API key, paste below. That's it!

        B. Gemini — FREE LLM (15 req/min)
           Sign up: https://aistudio.google.com/apikey

        C. Ollama — Fully offline, no API key needed
           Install: https://ollama.com
           Then run: ollama pull llama3.2

      OPTIONAL (Paid):
        D. Deepgram — Cloud STT ($0.0043/min, $200 free credit)
        E. OpenAI   — Cloud STT + LLM
        F. Anthropic — Cloud LLM
    """)

    # Read current config
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    # Groq key (recommended — covers both STT and LLM for free)
    groq_key = input("      Enter Groq API key (FREE — recommended, or Enter to skip): ").strip()
    if groq_key:
        config_text = config_text.replace(
            'groq_api_key = ""',
            f'groq_api_key = "{groq_key}"',
        )
        # Set Groq as default STT + polishing provider
        config_text = config_text.replace(
            'engine = "deepgram"',
            'engine = "groq"',
        )
        config_text = config_text.replace(
            'provider = "openai"',
            'provider = "groq"',
        )
        print("      [OK] Groq key saved (STT + AI polishing)")

    # Gemini key
    gemini_key = input("      Enter Gemini API key (FREE — or Enter to skip): ").strip()
    if gemini_key:
        config_text = config_text.replace(
            'gemini_api_key = ""',
            f'gemini_api_key = "{gemini_key}"',
        )
        if not groq_key:
            config_text = config_text.replace(
                'provider = "openai"',
                'provider = "gemini"',
            )
        print("      [OK] Gemini key saved")

    # Deepgram key (optional)
    dg_key = input("      Enter Deepgram API key (optional, or Enter to skip): ").strip()
    if dg_key:
        config_text = config_text.replace(
            'deepgram_api_key = ""',
            f'deepgram_api_key = "{dg_key}"',
            1,
        )
        print("      [OK] Deepgram key saved")

    # OpenAI key (optional)
    oai_key = input("      Enter OpenAI API key (optional, or Enter to skip): ").strip()
    if oai_key:
        config_text = config_text.replace(
            'openai_api_key = ""',
            f'openai_api_key = "{oai_key}"',
        )
        print("      [OK] OpenAI key saved")

    # Anthropic key (optional)
    ant_key = input("      Enter Anthropic API key (optional, or Enter to skip): ").strip()
    if ant_key:
        config_text = config_text.replace(
            'anthropic_api_key = ""',
            f'anthropic_api_key = "{ant_key}"',
        )
        print("      [OK] Anthropic key saved")

    # If no cloud keys at all, switch to offline mode
    if not groq_key and not dg_key and not oai_key:
        print("\n      No cloud STT key provided — switching to offline (whisper_local) mode")
        config_text = config_text.replace(
            'engine = "deepgram"',
            'engine = "whisper_local"',
        )
        if not groq_key and not gemini_key and not oai_key and not ant_key:
            config_text = config_text.replace(
                'provider = "groq"',
                'provider = "ollama"',
            )

    # Write updated config
    CONFIG_PATH.write_text(config_text, encoding="utf-8")
    print("      [OK] Config saved to config.toml")
    print()
    print("      [!] IMPORTANT: config.toml contains your API keys.")
    print("          NEVER share this file or commit it to git.")
    print("          It's already in .gitignore.")


def step5_verify():
    """Quick verification that imports work."""
    _print_step(5, "Verifying installation...")

    py = _get_python()
    test_code = """
import sys
sys.path.insert(0, r'{root}')
errors = []

# Core
try:
    from PyQt6.QtWidgets import QApplication
    print("      [OK] PyQt6")
except Exception as e:
    errors.append(f"PyQt6: {{e}}")
    print(f"      [FAIL] PyQt6: {{e}}")

try:
    import sounddevice
    print("      [OK] sounddevice")
except Exception as e:
    errors.append(f"sounddevice: {{e}}")
    print(f"      [FAIL] sounddevice: {{e}}")

try:
    import keyboard
    print("      [OK] keyboard")
except Exception as e:
    errors.append(f"keyboard: {{e}}")
    print(f"      [FAIL] keyboard: {{e}}")

try:
    import numpy
    print("      [OK] numpy")
except Exception as e:
    errors.append(f"numpy: {{e}}")
    print(f"      [FAIL] numpy: {{e}}")

try:
    import pyperclip
    print("      [OK] pyperclip")
except Exception as e:
    errors.append(f"pyperclip: {{e}}")
    print(f"      [FAIL] pyperclip: {{e}}")

# Optional
try:
    import torch
    print("      [OK] torch (offline mode available)")
except:
    print("      [--] torch not installed (offline mode unavailable)")

try:
    import faster_whisper
    print("      [OK] faster-whisper")
except:
    print("      [--] faster-whisper not installed")

try:
    import openai
    print("      [OK] openai")
except:
    print("      [--] openai not installed")

try:
    import deepgram
    print("      [OK] deepgram-sdk")
except:
    print("      [--] deepgram-sdk not installed")

if errors:
    print(f"\\n      [!] {{len(errors)}} required packages failed. Fix before running trevo.")
    sys.exit(1)
else:
    print("\\n      All required packages OK!")
""".format(root=str(ROOT).replace("\\", "\\\\"))

    _run([py, "-c", test_code])


def step6_instructions():
    """Print final instructions."""
    _print_step(6, "Setup complete!")

    py = _get_python()
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                  trevo is ready!                        ║
    ╠══════════════════════════════════════════════════════════╣
    ║                                                         ║
    ║  TO RUN:                                                ║
    ║    {py} main.py                       ║
    ║                                                         ║
    ║  TO BUILD .EXE:                                         ║
    ║    {py} build.py                      ║
    ║    (output: dist/trevo.exe)                             ║
    ║                                                         ║
    ║  HOW IT WORKS:                                          ║
    ║    1. trevo starts in the system tray (bottom-right)    ║
    ║    2. Press Ctrl+Shift+Space to start dictating         ║
    ║    3. A floating bar appears at the top of your screen  ║
    ║    4. Speak naturally — your words appear in real-time  ║
    ║    5. Press Ctrl+Shift+Space again to stop              ║
    ║    6. Polished text is pasted into whatever app you're  ║
    ║       typing in (email, Slack, VS Code, etc.)           ║
    ║                                                         ║
    ║  HOTKEYS:                                               ║
    ║    Ctrl+Shift+Space  = Start/stop dictation             ║
    ║    Ctrl+Shift+C      = Voice command mode               ║
    ║    Ctrl+Shift+M      = Mute/unmute                      ║
    ║    Escape             = Cancel                           ║
    ║                                                         ║
    ║  KNOWLEDGE VAULT:                                       ║
    ║    Your notes are saved as .md files at:                ║
    ║    ~/trevo-vault/                                       ║
    ║    Open this folder in Obsidian to browse them!         ║
    ║                                                         ║
    ║  SETTINGS:                                              ║
    ║    Right-click the tray icon > Settings                 ║
    ║    Or edit config.toml directly                         ║
    ║                                                         ║
    ╚══════════════════════════════════════════════════════════╝
    """)


def main():
    _print_header("trevo — First-Time Setup")
    print("  This wizard will set up everything you need to run trevo.")
    print("  It takes about 5 minutes.")
    print()

    step1_check_python()
    step2_create_venv()
    step3_install_deps()
    step4_setup_api_keys()
    step5_verify()
    step6_instructions()


if __name__ == "__main__":
    main()
