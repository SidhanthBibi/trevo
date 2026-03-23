"""First-time setup wizard for trevo.

Run this once to:
1. Find a compatible Python (3.11-3.13)
2. Create a virtual environment
3. Install dependencies (in parallel where possible)
4. Walk you through API key setup
5. Verify everything works
6. Launch the app
"""

import os
import shutil
import subprocess
import sys
import threading
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
    print(f"      > {' '.join(cmd[:6])}{'...' if len(cmd) > 6 else ''}")
    return subprocess.run(cmd, **kwargs)


# ---------------------------------------------------------------------------
# Step 1: Find a compatible Python
# ---------------------------------------------------------------------------

def _find_compatible_python() -> str:
    """Search for Python 3.11-3.13 on the system.

    Checks: current interpreter, `py` launcher, PATH pythons.
    Returns the path to the best candidate.
    """
    candidates: list[tuple[str, tuple[int, int, int]]] = []

    # Check current interpreter
    v = sys.version_info
    if 3 <= v.major and 11 <= v.minor <= 13:
        candidates.append((sys.executable, (v.major, v.minor, v.micro)))

    # Windows `py` launcher — try specific versions
    if sys.platform == "win32":
        for minor in (12, 11, 13):
            try:
                result = subprocess.run(
                    ["py", f"-3.{minor}", "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    ver_str = result.stdout.strip().split()[-1]  # "Python 3.12.1" -> "3.12.1"
                    parts = ver_str.split(".")
                    ver = (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
                    py_path = f"py -3.{minor}"
                    # Get the actual path
                    path_result = subprocess.run(
                        ["py", f"-3.{minor}", "-c", "import sys; print(sys.executable)"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if path_result.returncode == 0:
                        py_path = path_result.stdout.strip()
                    candidates.append((py_path, ver))
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    # Check PATH for python3.11, python3.12, python3.13
    for name in ("python3.12", "python3.11", "python3.13", "python3", "python"):
        path = shutil.which(name)
        if path and path not in [c[0] for c in candidates]:
            try:
                result = subprocess.run(
                    [path, "--version"], capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    ver_str = result.stdout.strip().split()[-1]
                    parts = ver_str.split(".")
                    ver = (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
                    if ver[0] == 3 and 11 <= ver[1] <= 13:
                        candidates.append((path, ver))
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    if not candidates:
        return ""

    # Prefer 3.12 > 3.11 > 3.13 (3.12 has best compatibility)
    def score(item):
        _, v = item
        preference = {12: 0, 11: 1, 13: 2}
        return preference.get(v[1], 99)

    candidates.sort(key=score)
    return candidates[0][0]


def step1_check_python() -> str:
    """Verify Python version and find the best interpreter."""
    _print_step(1, "Checking Python versions...")

    v = sys.version_info
    print(f"      Current interpreter: Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")

    if v.major == 3 and 11 <= v.minor <= 13:
        print(f"      [OK] Python {v.major}.{v.minor} is compatible!")
        return sys.executable

    # Current Python is not compatible — search for alternatives
    print(f"      [!] Python {v.major}.{v.minor} is NOT compatible (need 3.11-3.13)")
    print("      Searching for compatible Python installations...")

    best = _find_compatible_python()
    if best:
        print(f"      [OK] Found compatible Python: {best}")
        return best

    print()
    print("      [ERROR] No compatible Python found (3.11-3.13 required)")
    print()
    print("      Your installed Python versions:")
    # Show what's available
    if sys.platform == "win32":
        subprocess.run(["py", "--list"], capture_output=False)
    print()
    print("      Please install Python 3.12 from:")
    print("      https://www.python.org/downloads/release/python-3129/")
    print()
    print("      Then run this setup again.")
    sys.exit(1)


def step2_create_venv(python_exe: str):
    """Create virtual environment using the specified Python."""
    _print_step(2, "Creating virtual environment...")

    if VENV_DIR.exists():
        print(f"      .venv already exists at {VENV_DIR}")
        resp = input("      Recreate it? [y/N]: ").strip().lower()
        if resp != "y":
            print("      [SKIP]")
            return

    _run([python_exe, "-m", "venv", str(VENV_DIR)])
    print("      [OK] Virtual environment created")


def _get_pip() -> str:
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


def _get_python() -> str:
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def _install_group(pip: str, name: str, packages: list[str]) -> tuple[str, bool]:
    """Install a group of packages. Returns (group_name, success)."""
    result = subprocess.run(
        [pip, "install"] + packages,
        capture_output=True, text=True,
    )
    return (name, result.returncode == 0)


def step3_install_deps():
    """Install Python dependencies in parallel where possible."""
    _print_step(3, "Installing dependencies (parallel install)...")

    pip = _get_pip()

    # Upgrade pip first (must be sequential)
    print("      Upgrading pip...")
    _run([pip, "install", "--upgrade", "pip"], capture_output=True)

    # Define independent package groups for parallel install
    groups = {
        "Core UI": [
            "PyQt6>=6.6.0", "PyQt6-Frameless-Window>=0.4.0",
            "Pillow>=10.0.0",
        ],
        "Core System": [
            "keyboard>=0.13.5", "sounddevice>=0.4.6", "numpy>=1.24.0",
            "pyperclip>=1.8.2", "pyautogui>=0.9.54", "psutil>=5.9.0",
        ],
        "Core Utils": [
            "loguru>=0.7.0", "httpx>=0.27.0", "tomli>=2.0.0",
        ],
        "API Clients": [
            "openai>=1.30.0", "anthropic>=0.25.0",
        ],
        "TTS": [
            "gTTS>=2.3.0", "pyttsx3>=2.90",
        ],
        "Build Tools": [
            "pyinstaller>=6.0",
        ],
    }

    if sys.platform == "win32":
        groups["Windows"] = ["pywin32>=306"]

    # Run all groups in parallel
    print(f"      Installing {len(groups)} package groups in parallel...")
    results: list[tuple[str, bool]] = []
    threads: list[threading.Thread] = []

    def _worker(name, pkgs):
        r = _install_group(pip, name, pkgs)
        results.append(r)

    for name, pkgs in groups.items():
        t = threading.Thread(target=_worker, args=(name, pkgs))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Report results
    for name, success in sorted(results, key=lambda x: x[0]):
        status = "[OK]" if success else "[!] FAILED"
        print(f"      {status} {name}")

    failed = [name for name, success in results if not success]
    if failed:
        print(f"\n      [!] {len(failed)} group(s) had issues: {', '.join(failed)}")
        print("      The app may still work — try running it.")
    else:
        print("\n      [OK] All packages installed successfully!")

    # Optional: offline STT (large download, ask first)
    print("\n      Offline STT requires torch + faster-whisper (~2-4 GB download)")
    print("      NOTE: This is a very large download and is only needed for offline mode.")
    resp = input("      Install offline mode? [y/N]: ").strip().lower()
    if resp == "y":
        print("      Downloading torch + faster-whisper (this may take a while)...")
        result = _run(
            [pip, "install", "torch>=2.0.0", "faster-whisper>=1.0.0"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("      [!] torch/faster-whisper failed — offline mode unavailable")
            print("      Cloud STT will still work fine.")
        else:
            print("      [OK] Offline STT ready")
    else:
        print("      [SKIP] Offline mode skipped")


def step4_setup_api_keys():
    """Walk user through API key configuration."""
    _print_step(4, "Setting up API keys...")

    if not CONFIG_PATH.exists():
        # Copy from example if available
        example = ROOT / "config.toml.example"
        if example.exists():
            shutil.copy2(example, CONFIG_PATH)
        else:
            print("      [!] config.toml not found. Skipping API key setup.")
            print("      You can configure keys later in Settings.")
            return

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

      OPTIONAL (Paid / Subscription):
        D. OpenAI   — Cloud STT + LLM (or use ChatGPT Plus plan)
        E. Anthropic — Cloud LLM (or use Claude Pro plan)

      TIP: If you have Claude Pro or ChatGPT Plus, you can use those
      subscriptions instead of API keys — see README for details.
    """)

    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    # Groq key
    groq_key = input("      Enter Groq API key (FREE — recommended, or Enter to skip): ").strip()
    if groq_key:
        config_text = config_text.replace('groq_api_key = ""', f'groq_api_key = "{groq_key}"')
        print("      [OK] Groq key saved (STT + AI polishing)")

    # Gemini key
    gemini_key = input("      Enter Gemini API key (FREE — or Enter to skip): ").strip()
    if gemini_key:
        config_text = config_text.replace('gemini_api_key = ""', f'gemini_api_key = "{gemini_key}"')
        if not groq_key:
            config_text = config_text.replace('provider = "groq"', 'provider = "gemini"')
        print("      [OK] Gemini key saved")

    # OpenAI key
    oai_key = input("      Enter OpenAI API key (optional, or Enter to skip): ").strip()
    if oai_key:
        config_text = config_text.replace('openai_api_key = ""', f'openai_api_key = "{oai_key}"')
        print("      [OK] OpenAI key saved")

    # Anthropic key
    ant_key = input("      Enter Anthropic API key (optional, or Enter to skip): ").strip()
    if ant_key:
        config_text = config_text.replace('anthropic_api_key = ""', f'anthropic_api_key = "{ant_key}"')
        print("      [OK] Anthropic key saved")

    # Memory vault location
    print()
    default_vault = str(Path.home() / "trevo-vault")
    vault_path = input(f"      Memory Vault location [{default_vault}]: ").strip()
    if not vault_path:
        vault_path = default_vault
    # Ensure vault directory exists
    Path(vault_path).mkdir(parents=True, exist_ok=True)
    if 'vault_path' in config_text:
        # Replace existing vault_path
        import re
        config_text = re.sub(
            r'vault_path\s*=\s*"[^"]*"',
            f'vault_path = "{vault_path}"',
            config_text,
        )
    else:
        config_text += f'\n[knowledge]\nvault_path = "{vault_path}"\n'

    # If no cloud keys at all, switch to offline mode
    if not groq_key and not oai_key:
        print("\n      No cloud STT key provided — switching to offline (whisper_local) mode")
        config_text = config_text.replace('engine = "groq"', 'engine = "whisper_local"')
        if not groq_key and not gemini_key and not oai_key and not ant_key:
            config_text = config_text.replace('provider = "groq"', 'provider = "ollama"')

    CONFIG_PATH.write_text(config_text, encoding="utf-8")
    print("\n      [OK] Config saved to config.toml")
    print("      [!] IMPORTANT: config.toml contains your API keys.")
    print("          NEVER share this file or commit it to git.")


def step5_verify():
    """Quick verification that imports work."""
    _print_step(5, "Verifying installation...")

    py = _get_python()
    test_code = """
import sys
sys.path.insert(0, r'{root}')
errors = []

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

if errors:
    print(f"\\n      [!] {{len(errors)}} required packages failed. Fix before running trevo.")
    sys.exit(1)
else:
    print("\\n      All required packages OK!")
    sys.exit(0)
""".format(root=str(ROOT).replace("\\", "\\\\"))

    try:
        result = _run([py, "-c", test_code])
        if result.returncode != 0:
            print("      [!] Verification encountered issues (see above)")
    except Exception as e:
        print(f"      [!] Verification failed: {e}")
        print("      The app may still work — try running it.")


def step6_launch():
    """Offer to launch trevo."""
    _print_step(6, "Setup complete!")

    py = _get_python()
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                  trevo is ready!                        ║
    ╠══════════════════════════════════════════════════════════╣
    ║                                                         ║
    ║  TO RUN:                                                ║
    ║    {py:<50s} ║
    ║    main.py                                              ║
    ║                                                         ║
    ║  TO BUILD .EXE:                                         ║
    ║    {py:<50s} ║
    ║    build.py                                             ║
    ║                                                         ║
    ║  HOTKEYS:                                               ║
    ║    Ctrl+Shift+Space  = Start/stop dictation             ║
    ║    Ctrl+Shift+C      = Voice command mode               ║
    ║    Ctrl+Shift+T      = Trevo Mode (JARVIS sphere)       ║
    ║    Escape             = Cancel                           ║
    ║                                                         ║
    ║  SETTINGS:                                              ║
    ║    Right-click the tray icon > Settings                 ║
    ║    Or edit config.toml directly                         ║
    ║                                                         ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    resp = input("      Launch trevo now? [Y/n]: ").strip().lower()
    if resp != "n":
        print("      Starting trevo...")
        launch_cmd = [py, str(ROOT / "main.py")]
        print(f"      Command: {' '.join(launch_cmd)}")
        try:
            subprocess.Popen(launch_cmd)
            print("      [OK] trevo is running in the system tray!")
        except Exception as e:
            print(f"      [!] Failed to launch trevo: {e}")
            print(f"      Run manually with: {py} main.py")
    else:
        print(f"      Run later with: {py} main.py")


def main():
    _print_header("trevo — First-Time Setup")
    print("  This wizard will set up everything you need to run trevo.")
    print()

    python_exe = step1_check_python()
    step2_create_venv(python_exe)
    step3_install_deps()
    step4_setup_api_keys()
    step5_verify()
    step6_launch()

    input("\n      Press Enter to exit...")


if __name__ == "__main__":
    main()
