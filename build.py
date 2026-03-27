"""Build script for trevo — creates standalone .exe + Windows installer.

Usage:
    python build.py          # Build .exe only
    python build.py --all    # Build .exe + installer
    python build.py --exe    # Build .exe only (same as default)
    python build.py --installer  # Build installer only (requires .exe exists)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build_exe() -> Path:
    """Build trevo.exe using PyInstaller."""
    print("\n" + "=" * 60)
    print("  Building trevo.exe with PyInstaller")
    print("=" * 60)

    # Ensure assets directory exists
    assets_dir = ROOT / "ui" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Generate a basic icon if none exists
    icon_path = assets_dir / "icon.ico"
    if not icon_path.exists():
        _generate_icon(icon_path)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "trevo",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",

        # Exclude heavy ML packages — speaker recognition deferred to future release
        "--exclude-module", "torch",
        "--exclude-module", "torchvision",
        "--exclude-module", "torchaudio",
        "--exclude-module", "resemblyzer",
        "--exclude-module", "librosa",
        "--exclude-module", "numba",
        "--exclude-module", "llvmlite",
        "--exclude-module", "sklearn",
        "--exclude-module", "scikit-learn",
        "--exclude-module", "scipy",
        "--exclude-module", "webrtcvad",
        "--exclude-module", "soundfile",
        "--exclude-module", "tensorflow",
        "--exclude-module", "tensorboard",
        "--exclude-module", "tkinter",
        "--exclude-module", "_tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "IPython",
        "--exclude-module", "notebook",
        "--exclude-module", "pytest",

        # Hidden imports for all our packages
        "--hidden-import", "core",
        "--hidden-import", "core.app",
        "--hidden-import", "core.audio_capture",
        "--hidden-import", "core.vad",
        "--hidden-import", "core.stt_engine",
        "--hidden-import", "core.stt_gemini",
        "--hidden-import", "core.stt_google",
        "--hidden-import", "core.stt_whisper",
        "--hidden-import", "core.stt_openai",
        "--hidden-import", "core.stt_groq",
        "--hidden-import", "core.text_polisher",
        "--hidden-import", "core.text_injector",
        "--hidden-import", "core.context_detector",
        "--hidden-import", "core.command_parser",
        "--hidden-import", "core.conversation_engine",
        "--hidden-import", "core.language_manager",
        "--hidden-import", "core.hotkey_manager",
        "--hidden-import", "ui",
        "--hidden-import", "ui.tray_icon",
        "--hidden-import", "ui.dictation_bar",
        "--hidden-import", "ui.settings_dialog",
        "--hidden-import", "ui.transcript_viewer",
        "--hidden-import", "ui.styles",
        "--hidden-import", "models",
        "--hidden-import", "models.settings",
        "--hidden-import", "models.transcript",
        "--hidden-import", "models.custom_dictionary",
        "--hidden-import", "storage",
        "--hidden-import", "storage.database",
        "--hidden-import", "storage.migrations",
        "--hidden-import", "knowledge",
        "--hidden-import", "knowledge.graph",
        "--hidden-import", "knowledge.note",
        "--hidden-import", "knowledge.daily",
        "--hidden-import", "utils",
        "--hidden-import", "utils.audio_utils",
        "--hidden-import", "utils.text_utils",
        "--hidden-import", "utils.platform_utils",
        "--hidden-import", "utils.logger",

        # Agent and automation modules
        "--hidden-import", "core.agent_mode",
        "--hidden-import", "core.desktop_automation",
        "--hidden-import", "core.stt_gemini",
        "--hidden-import", "core.stt_google",
        "--hidden-import", "core.workflow_engine",
        "--hidden-import", "ui.workflow_editor",
        "--hidden-import", "ui.trevo_mode",
        "--hidden-import", "core.tts_engine",
        "--hidden-import", "core.clap_detector",
        "--hidden-import", "core.wake_word",
        # core.speaker_recognition excluded — depends on torch (deferred)
        "--hidden-import", "pynput",
        "--hidden-import", "pynput.keyboard",
        "--hidden-import", "pynput.keyboard._win32",
        "--hidden-import", "mcp_server",
        "--hidden-import", "mcp_server.server",

        # Add asset files
        "--add-data", f"{ROOT / 'ui' / 'assets'};ui/assets",

        # Icon
        "--icon", str(icon_path),

        # Entry point
        str(ROOT / "main.py"),
    ]

    print(f"\n  Running PyInstaller...")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("\n  [FAILED] PyInstaller failed. Check errors above.")
        sys.exit(1)

    dist_dir = ROOT / "dist" / "trevo"
    exe_path = dist_dir / "trevo.exe"

    # Copy config template next to exe
    config_example = ROOT / "config.toml.example"
    if config_example.exists():
        shutil.copy2(config_example, dist_dir / "config.toml")
        print(f"  Copied config.toml to dist/trevo/")

    print(f"\n  [OK] Built: {exe_path}")
    print(f"  Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    return exe_path


def build_installer() -> Path:
    """Build Windows installer using Inno Setup."""
    print("\n" + "=" * 60)
    print("  Building Windows Installer")
    print("=" * 60)

    exe_path = ROOT / "dist" / "trevo" / "trevo.exe"
    if not exe_path.exists():
        print("  [!] trevo.exe not found. Building it first...")
        build_exe()

    iss_path = ROOT / "installer.iss"
    if not iss_path.exists():
        print("  [FAILED] installer.iss not found")
        sys.exit(1)

    # Try to find Inno Setup compiler
    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("iscc") or "",
    ]

    iscc = None
    for p in iscc_paths:
        if p and Path(p).exists():
            iscc = p
            break

    if not iscc:
        print("""
  [!] Inno Setup not found. To build the installer:

  1. Download Inno Setup from: https://jrsoftware.org/isdl.php
  2. Install it (default location is fine)
  3. Run this command again

  OR open installer.iss directly in Inno Setup Compiler and click Build.

  For now, you can distribute these files manually:
    dist/trevo.exe
    dist/config.toml
        """)
        return ROOT / "dist"

    # Create output directory
    output_dir = ROOT / "installer_output"
    output_dir.mkdir(exist_ok=True)

    cmd = [iscc, str(iss_path)]
    print(f"  Running Inno Setup Compiler...")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print("  [FAILED] Installer build failed.")
        sys.exit(1)

    installer = output_dir / "trevo-setup-1.0.0.exe"
    print(f"\n  [OK] Installer built: {installer}")
    if installer.exists():
        print(f"  Size: {installer.stat().st_size / 1024 / 1024:.1f} MB")
    return installer


def _generate_icon(path: Path) -> None:
    """Generate a simple app icon programmatically."""
    try:
        from PIL import Image, ImageDraw

        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Dark blue circle background
        margin = 20
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(26, 26, 46, 255),
            outline=(233, 69, 96, 255),
            width=4,
        )

        # "T" for trevo in the center
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("segoeui.ttf", 120)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "T", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
            "T",
            fill=(233, 69, 96, 255),
            font=font,
        )

        img.save(str(path), format="ICO", sizes=[(256, 256), (48, 48), (32, 32), (16, 16)])
        print(f"  Generated icon: {path}")
    except ImportError:
        print("  [!] Pillow not installed — skipping icon generation")
        # Create a minimal valid .ico (1x1 pixel)
        ico_data = bytes([
            0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 32, 0,
            68, 0, 0, 0, 22, 0, 0, 0, 40, 0, 0, 0, 1, 0,
            0, 0, 2, 0, 0, 0, 1, 0, 32, 0, 0, 0, 0, 0,
            4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 233, 69, 96, 255, 0, 0, 0, 0,
        ])
        path.write_bytes(ico_data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build trevo for distribution")
    parser.add_argument("--all", action="store_true", help="Build .exe + installer")
    parser.add_argument("--exe", action="store_true", help="Build .exe only (default)")
    parser.add_argument("--installer", action="store_true", help="Build installer only")
    args = parser.parse_args()

    if args.installer:
        build_installer()
    elif args.all:
        build_exe()
        build_installer()
    else:
        build_exe()

    print("\n" + "=" * 60)
    print("  Done!")
    print("=" * 60)
    print("""
  DISTRIBUTION OPTIONS:

  Option 1: Simple (no installer)
    Copy dist/trevo.exe + dist/config.toml to any Windows PC.
    Edit config.toml with API keys, double-click trevo.exe.

  Option 2: Installer (.exe setup wizard)
    Run: python build.py --all
    Share installer_output/trevo-setup-1.0.0.exe
    User runs it, enters API keys when prompted.

  Option 3: Fully offline (no API keys needed)
    Set engine = "whisper_local" in config.toml
    Set provider = "ollama" in config.toml
    Install Ollama on each PC: https://ollama.com
    Run: ollama pull llama3.2
    """)


if __name__ == "__main__":
    main()
