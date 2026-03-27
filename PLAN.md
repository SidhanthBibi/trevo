# trevo — Master Roadmap

> Rule: NEVER delete entries from this file. Only check off completed items.

---

## Phase 1: Core Voice-to-Text Pipeline (COMPLETE)

- [x] Audio capture with sounddevice callback
- [x] Voice Activity Detection (Silero → webrtcvad → energy fallback)
- [x] STT: Google Cloud Speech-to-Text (free 60 min/month, primary engine)
- [x] STT: faster-whisper (local, offline)
- [x] STT: OpenAI Whisper API (cloud)
- [x] STT: Groq Whisper (free cloud, 30 req/min)
- [x] STT: Gemini multimodal (built, not wired)
- [x] STT: Google Cloud Speech-to-Text (built, not wired)
- [x] Text polishing with LLM (OpenAI, Anthropic, Ollama, Groq, Gemini)
- [x] Conversation Engine — intent detection (dictate/instruct/edit/meta/conversation)
- [x] Multi-turn context with draft history and undo
- [x] Text injection via clipboard with save/restore
- [x] Global hotkeys (toggle + push-to-talk)
- [x] Command parser (11 edit + 16 dictation commands)
- [x] Context detector (active window detection)
- [x] Language manager (20+ languages)
- [x] SQLite database with WAL mode and migrations
- [x] Knowledge vault (Obsidian-compatible .md files, wikilinks, backlinks, daily notes)
- [x] Glassmorphism UI: DictationBar, TrayIcon, SettingsDialog, TranscriptViewer
- [x] PyInstaller build script
- [x] Inno Setup Windows installer with API key wizard
- [x] config.toml with TOML parsing and Settings dataclass
- [x] First-time setup wizard (setup_trevo.py)

---

## Phase 2: Trevo Mode + Workflows + Integration (IN PROGRESS)

### 2.0 Fix & Integrate Dead Code
- [x] Wire stt_gemini.py into app.py (fix hardcoded model URL)
- [x] Wire stt_google.py into app.py (fix encoding mismatch)
- [x] Wire agent_mode.py into app.py (add AGENT_MODE state)
- [x] Sync config.toml with config.toml.example
- [x] Add gemini_api_key to STTSettings
- [x] Add Gemini/Google Cloud to settings dialog STT dropdown
- [x] Update build.py hidden imports for all new modules
- [x] Fix unnecessary getattr calls in app.py
- [x] Fix workflow_editor.py broken import path (trevo.core → core)
- [x] Fix glPointSize inside glBegin/glEnd (OpenGL spec violation)
- [x] Fix settings_dialog missing Gemini/Google Cloud key save/load
- [x] Fix double-prefix "Engine: Engine:" in tray menu
- [x] Fix dictation_bar _ui_font never iterating fallbacks
- [x] Fix settings dialog not passing/persisting current settings
- [x] Fix workflow_editor asyncio.run blocking Qt event loop

### 2.1 Trevo Mode (JARVIS Particle Sphere)
- [x] Create ui/trevo_mode.py — QOpenGLWidget particle sphere
- [x] 200-500 particles on sphere with sin/cos displacement animation
- [x] State-based colors: IDLE=blue, LISTENING=green, PROCESSING=orange, SPEAKING=purple, ERROR=red
- [x] Inner core glow via additive blending
- [x] Frameless, semi-transparent, always-on-top window
- [x] Activate only on Ctrl+Shift+T or wake phrase
- [x] "Wake up daddy's home" trigger → morning briefing workflow
- [ ] Morning briefing: news (RSS), weather (wttr.in), open browser tabs
- [ ] "No tabs today" session flag support
- [ ] Always-on conversation mode with VAD hot mic

### 2.2 TTS Engine
- [x] Create core/tts_engine.py with TTSEngine ABC
- [x] GoogleCloudTTS (WaveNet, FREE 1M chars/month)
- [x] FreeTTS (gTTS, no API key needed)
- [x] OfflineTTS (pyttsx3, Windows SAPI)
- [x] Fallback chain: Google Cloud → gTTS → pyttsx3
- [ ] Add [tts] section to config.toml
- [ ] Audio playback via sounddevice

### 2.3 Clap Detection
- [x] Create core/clap_detector.py
- [x] Bandpass filter 1-5kHz
- [x] Double-clap detection (2 spikes within 300-600ms)
- [x] Debounce (2s cooldown)
- [x] Emit clap_detected signal → toggle Trevo Mode
- [ ] Configurable sensitivity in settings

### 2.4 Speaker Recognition
- [x] Create core/speaker_recognition.py
- [x] Voice embedding via resemblyzer (256-dim vectors)
- [x] Enrollment: "my name is X" → save embedding to ~/trevo-vault/voices/
- [x] Runtime: compare embeddings (cosine similarity > 0.75)
- [ ] Per-user profiles with preferences
- [ ] Greeting by name in Trevo Mode

### 2.5 Workflow Editor Integration
- [x] Wire workflow_editor.py into main.py tray menu
- [ ] Connect STTExecutor to real STT engines
- [ ] Connect LLMExecutor to real ConversationEngine._call_llm()
- [ ] Connect TextInjectExecutor to real TextInjector
- [ ] Fix Smart Assistant preset (add Merge node)
- [ ] Use loguru instead of stdlib logging in workflow_engine.py

### 2.6 ShadCN-Style Settings
- [ ] Integrate custom-ui-pyqt6 package for glassmorphism widgets
- [ ] Restyle settings dialog pages with ShadCN-inspired components
- [ ] Add Trevo Mode settings page (sphere style, wake phrase, clap sensitivity)
- [ ] Add TTS settings page (provider, voice, language)

### 2.7 Installer & First-Run
- [x] Add Memory Vault location wizard page to installer.iss
- [x] Create ui/first_run.py — QWizard first-run experience
- [x] Pages: Welcome → API Keys → Memory Vault → Voice Enrollment → Done
- [x] Add Memory Vault path to setup_trevo.py
- [x] Add Terms & Conditions and Privacy Policy
- [x] Fix setup_trevo.py Python version detection (find 3.11-3.13)
- [x] Parallel dependency installation in setup_trevo.py
- [x] Launch app after setup completion
- [ ] Add [knowledge] section to config.toml with vault_path

### 2.8 MCP Server
- [x] Create mcp_server/ directory
- [x] Create mcp_server/server.py with FastMCP
- [x] Tool: get_status (app state, engine, etc.)
- [x] Tool: search_vault (search knowledge notes)
- [x] Tool: trigger_workflow (run named workflow)
- [x] Tool: get_transcript_history (query recent transcripts)
- [x] Document Claude Remote Mode limitation (first-party only)

### 2.9 Security & Quality
- [x] Fix command injection in desktop_automation.py (shell=True with user input)
- [x] Sandbox exec() in workflow_engine.py custom nodes
- [x] Create fail.md (dead code audit)
- [x] Create PLAN.md (this file)
- [x] Update requirements.txt with all new dependencies
- [x] Fix shell=True → shlex.split + shell=False in desktop_automation.py
- [x] Add shell metacharacter rejection for safe commands
- [x] Redact API keys in MCP server get_settings() response
- [x] Cleaned up unused STT providers
- [x] Add TTS and Knowledge sections to settings model
- [ ] API keys in Windows Credential Store (no plaintext)

### 2.10 Git & Release
- [x] git init
- [x] Update .gitignore (installer_output/, voices/)
- [x] Initial commit: trevo v1.0.0
- [x] Tag: v1.0.0
- [x] Create GitHub repo: sidhanthbibi/trevo
- [x] Push to GitHub
- [x] v1.0.1: Security fixes, docs update, cleanup

### 2.11 Claude Pro / ChatGPT Plus Integration
- [x] Agent mode uses `claude` CLI for agentic tasks (no API key needed)
- [ ] Add browser-based ChatGPT integration via playwright/selenium
- [ ] Add option to route LLM calls through subscription plans
- [ ] Settings UI for choosing "API key" vs "Subscription plan" mode

---

## Phase 3: Future (Not Started)

### Cross-Platform
- [ ] macOS support (replace pywin32, test PyInstaller on Mac)
- [ ] Linux support (PulseAudio/PipeWire, .deb/.AppImage packaging)
- [ ] Mobile companion app (React Native or Flutter)
- [ ] Phone companion app that connects to desktop trevo via WebSocket

### Advanced AI
- [ ] Agent Mode Phase 2 — multi-step task execution
- [ ] Claude Code CLI integration via subprocess
- [ ] Codex CLI integration
- [ ] Advanced workflow AI — self-improving pipelines
- [ ] RAG over knowledge vault (embed notes, semantic search)

### Platform
- [ ] Windows credential store for API keys (no plaintext)
- [ ] Auto-update mechanism
- [ ] Plugin system for custom nodes
- [ ] Community workflow marketplace
- [ ] Electron/Tauri rewrite for web tech UI (evaluate vs PyQt6)

### Voice
- [ ] Wake word detection (custom "Hey Trevo" model)
- [ ] Emotion detection from voice
- [ ] Voice cloning for personalized TTS
- [ ] Multi-language conversation (auto-detect and switch)

### Connectivity
- [ ] Phone-to-desktop WebSocket bridge (mic on phone → STT on desktop)
- [ ] REST API for remote control
- [ ] Web dashboard for transcript history
- [ ] Cross-device sync for Memory Vault
