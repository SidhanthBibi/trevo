# trevo

**Voice-to-text desktop application with conversational AI, JARVIS-style Trevo Mode, and visual workflow editor.**

trevo captures your voice, transcribes it in real-time using cloud or local STT engines, polishes the text with AI, and pastes it wherever you're typing. It also features a JARVIS-inspired particle sphere (Trevo Mode), knowledge vault, speaker recognition, and a node-based workflow editor.

Built with Python 3.11+ and PyQt6. Windows-first, with cross-platform planned.

---

## Features

- **Voice-to-Text** — Speak naturally, get polished text pasted into any app
- **6 STT Engines** — Groq (free), Deepgram, OpenAI, Gemini, Google Cloud, faster-whisper (offline)
- **AI Text Polishing** — Grammar, punctuation, formatting via Groq/Gemini/Ollama/OpenAI/Anthropic
- **Trevo Mode** — JARVIS-style 3D particle sphere with voice interaction ("Wake up daddy's home")
- **Conversation Engine** — Intent detection: dictate, instruct, edit, meta, conversation
- **Knowledge Vault** — Obsidian-compatible .md files with wikilinks, backlinks, daily notes
- **Workflow Editor** — DaVinci Resolve-style visual node editor for custom voice pipelines
- **Speaker Recognition** — Voice enrollment and per-user identification
- **Clap Detection** — Double-clap to activate Trevo Mode
- **TTS Engine** — Google Cloud WaveNet (free 1M chars/month), gTTS, pyttsx3 fallback
- **MCP Server** — Claude Code integration via FastMCP

---

## Quick Start

### Option 1: Windows Installer (Recommended)

1. Download `trevo-setup-1.0.0.exe` from [Releases](https://github.com/sidhanthbibi/trevo/releases)
2. Run the installer — it will ask for:
   - Speech engine selection (Groq recommended — free)
   - AI polishing provider (Groq recommended — free)
   - API keys (get a free Groq key at https://console.groq.com)
   - Memory Vault location (default: `~/trevo-vault/`)
3. Launch trevo from the Start Menu or desktop shortcut
4. Press **Ctrl+Shift+Space** to start dictating

### Option 2: From Source (Developer Setup)

```bash
# Clone the repo
git clone https://github.com/sidhanthbibi/trevo.git
cd trevo

# Run the setup wizard (finds compatible Python, creates venv, installs deps)
python setup_trevo.py

# Or manual setup:
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
python main.py
```

### Option 3: Build Your Own Installer

```bash
# Activate venv
.venv\Scripts\activate

# Build .exe only
python build.py

# Build .exe + Windows installer
python build.py --all

# Output:
#   dist/trevo.exe                        (standalone executable)
#   installer_output/trevo-setup-1.0.0.exe (Windows installer)
```

**Requirements for building the installer:**
- [Inno Setup 6](https://jrsoftware.org/isdl.php) — download and install, then run `python build.py --all`

---

## How It Works

1. **trevo starts in the system tray** (bottom-right of your screen)
2. Press **Ctrl+Shift+Space** to start dictating
3. A floating glassmorphism bar appears at the top of your screen
4. Speak naturally — your words appear in real-time
5. Press **Ctrl+Shift+Space** again to stop
6. AI-polished text is automatically pasted into whatever app you're using

### Hotkeys

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+Space` | Start/stop dictation |
| `Ctrl+Shift+C` | Voice command mode |
| `Ctrl+Shift+T` | Toggle Trevo Mode (JARVIS sphere) |
| `Escape` | Cancel current recording |

### Trevo Mode

Press **Ctrl+Shift+T** or double-clap to activate the JARVIS-style particle sphere. Say "Wake up daddy's home" to trigger the morning briefing workflow.

The sphere changes color based on state:
- Blue = Idle
- Green = Listening
- Orange = Processing
- Purple = Speaking
- Red = Error

---

## Using Your Claude Pro / ChatGPT Plus Subscription

trevo supports using your existing subscriptions instead of API keys:

### Claude Pro (via Claude Code CLI)

trevo's Agent Mode already routes complex tasks through the `claude` CLI, which uses your Claude Pro subscription — **no API key needed**.

1. Install Claude Code: `npm install -g @anthropic-ai/claude-code`
2. Authenticate: `claude auth`
3. In trevo, complex voice commands are automatically routed to Claude

### ChatGPT Plus (Planned)

Browser-based integration with ChatGPT Plus is planned for a future update. For now, you can use the OpenAI API with your API key.

### Free Tier (No Payment Required)

For zero-cost usage:
- **STT**: Groq Whisper (free, 30 req/min)
- **LLM**: Groq (free, 30 req/min) or Ollama (local, unlimited)
- **TTS**: Google Cloud WaveNet (free 1M chars/month) or gTTS

---

## Project Structure

```
trevo/
├── main.py                 # Entry point — wires everything together
├── config.toml             # User configuration (API keys, preferences)
├── setup_trevo.py          # First-time setup wizard
├── build.py                # PyInstaller + Inno Setup build script
├── installer.iss           # Inno Setup installer script
├── requirements.txt        # Python dependencies
├── PLAN.md                 # Master roadmap with checkboxes
├── fail.md                 # Bug audit and known issues
├── TERMS.txt               # Terms and Conditions
├── PRIVACY.txt             # Privacy Policy
│
├── core/                   # Core engine modules
│   ├── app.py              # TrevoApp — central controller
│   ├── audio_capture.py    # Microphone capture with sounddevice
│   ├── vad.py              # Voice Activity Detection
│   ├── stt_engine.py       # STT base class
│   ├── stt_deepgram.py     # Deepgram Nova-3 (streaming)
│   ├── stt_groq.py         # Groq Whisper (free)
│   ├── stt_openai.py       # OpenAI Whisper API
│   ├── stt_gemini.py       # Gemini multimodal STT
│   ├── stt_google.py       # Google Cloud STT
│   ├── stt_whisper.py      # faster-whisper (local/offline)
│   ├── text_polisher.py    # AI text polishing
│   ├── text_injector.py    # Clipboard-based text injection
│   ├── conversation_engine.py  # Intent detection + LLM routing
│   ├── command_parser.py   # Voice command parsing
│   ├── context_detector.py # Active window detection
│   ├── language_manager.py # Multi-language support
│   ├── hotkey_manager.py   # Global hotkey registration
│   ├── tts_engine.py       # Text-to-speech (Google/gTTS/pyttsx3)
│   ├── clap_detector.py    # Double-clap detection
│   ├── speaker_recognition.py  # Voice enrollment + identification
│   ├── agent_mode.py       # Agent orchestrator (Groq + Claude CLI)
│   ├── desktop_automation.py   # Safe desktop operations
│   └── workflow_engine.py  # 15-node workflow execution engine
│
├── ui/                     # PyQt6 UI components
│   ├── dictation_bar.py    # Floating glassmorphism dictation overlay
│   ├── tray_icon.py        # System tray icon + menu
│   ├── settings_dialog.py  # Settings dialog (tabbed)
│   ├── transcript_viewer.py # Transcript history viewer
│   ├── trevo_mode.py       # JARVIS particle sphere (OpenGL + QPainter)
│   ├── workflow_editor.py  # Visual node-based workflow editor
│   ├── first_run.py        # First-run QWizard
│   └── styles.py           # Dark/light theme stylesheets
│
├── models/                 # Data models
│   ├── settings.py         # Settings dataclass + TOML parsing
│   ├── transcript.py       # Transcript data model
│   └── custom_dictionary.py
│
├── storage/                # Persistence
│   ├── database.py         # SQLite with WAL mode
│   └── migrations.py       # Schema migrations
│
├── knowledge/              # Knowledge vault (Obsidian-compatible)
│   ├── graph.py            # Wikilink graph + backlinks
│   ├── note.py             # Note CRUD operations
│   └── daily.py            # Daily notes
│
├── mcp_server/             # MCP server for Claude Code integration
│   └── server.py           # FastMCP with 7 tools
│
└── utils/                  # Utilities
    ├── logger.py           # Loguru configuration
    ├── text_utils.py       # Text processing helpers
    ├── audio_utils.py      # Audio format conversion
    └── platform_utils.py   # OS-specific helpers
```

---

## Configuration

Edit `config.toml` directly or use Settings (right-click tray icon):

```toml
[general]
hotkey = "ctrl+shift+space"
theme = "dark"

[stt]
engine = "groq"                    # groq, deepgram, whisper_local, openai, gemini, google_cloud
groq_api_key = "gsk_..."          # Free at console.groq.com

[polishing]
enabled = true
provider = "groq"                  # groq, gemini, ollama, openai, anthropic
groq_api_key = "gsk_..."

[knowledge]
vault_path = "C:/Users/you/trevo-vault"
```

---

## MCP Server (Claude Code Integration)

trevo includes an MCP server for integration with Claude Code:

```bash
# Run the MCP server
python -m mcp_server.server

# Available tools:
# - get_status: App state, engine info
# - search_vault: Search knowledge notes
# - get_vault_note: Read a specific note
# - list_workflows: List available workflows
# - get_transcript_history: Query recent transcripts
# - get_settings: Read current settings
# - update_setting: Modify a setting
```

---

## Privacy

- All data stays on your machine
- Audio is only captured when you activate recording
- No analytics, no telemetry, no accounts
- API keys stored locally in config.toml
- See [PRIVACY.txt](PRIVACY.txt) for full details

---

## License

MIT License. See [TERMS.txt](TERMS.txt).

---

## Requirements

- Windows 10/11 (64-bit)
- Python 3.11-3.13 (for development)
- Microphone
- Internet (for cloud STT/LLM) or Ollama (for offline mode)
