# trevo — Master Roadmap

> Rule: NEVER delete entries from this file. Only check off completed items.

---

## Phase 1: Core Voice-to-Text Pipeline (COMPLETE)

- [x] Audio capture with sounddevice callback
- [x] Voice Activity Detection (Silero → webrtcvad → energy fallback)
- [x] STT: Deepgram Nova-3 (cloud, streaming)
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
- [ ] Wire stt_gemini.py into app.py (fix hardcoded model URL)
- [ ] Wire stt_google.py into app.py (fix encoding mismatch)
- [ ] Wire agent_mode.py into app.py (add AGENT_MODE state)
- [ ] Sync config.toml with config.toml.example
- [ ] Add gemini_api_key to STTSettings
- [ ] Add Gemini/Google Cloud to settings dialog STT dropdown
- [ ] Update build.py hidden imports for all new modules
- [ ] Fix unnecessary getattr calls in app.py

### 2.1 Trevo Mode (JARVIS Particle Sphere)
- [ ] Create ui/trevo_mode.py — QOpenGLWidget particle sphere
- [ ] 200-500 particles on sphere with sin/cos displacement animation
- [ ] State-based colors: IDLE=blue, LISTENING=green, PROCESSING=orange, SPEAKING=purple, ERROR=red
- [ ] Inner core glow via additive blending
- [ ] Frameless, semi-transparent, always-on-top window
- [ ] Activate only on Ctrl+Shift+T or wake phrase
- [ ] "Wake up daddy's home" trigger → morning briefing workflow
- [ ] Morning briefing: news (RSS), weather (wttr.in), open browser tabs
- [ ] "No tabs today" session flag support
- [ ] Always-on conversation mode with VAD hot mic

### 2.2 TTS Engine
- [ ] Create core/tts_engine.py with TTSEngine ABC
- [ ] GoogleCloudTTS (WaveNet, FREE 1M chars/month)
- [ ] FreeTTS (gTTS, no API key needed)
- [ ] OfflineTTS (pyttsx3, Windows SAPI)
- [ ] Fallback chain: Google Cloud → gTTS → pyttsx3
- [ ] Add [tts] section to config.toml
- [ ] Audio playback via sounddevice

### 2.3 Clap Detection
- [ ] Create core/clap_detector.py
- [ ] Bandpass filter 1-5kHz
- [ ] Double-clap detection (2 spikes within 300-600ms)
- [ ] Debounce (2s cooldown)
- [ ] Emit clap_detected signal → toggle Trevo Mode
- [ ] Configurable sensitivity in settings

### 2.4 Speaker Recognition
- [ ] Create core/speaker_recognition.py
- [ ] Voice embedding via resemblyzer (256-dim vectors)
- [ ] Enrollment: "my name is X" → save embedding to ~/trevo-vault/voices/
- [ ] Runtime: compare embeddings (cosine similarity > 0.75)
- [ ] Per-user profiles with preferences
- [ ] Greeting by name in Trevo Mode

### 2.5 Workflow Editor Integration
- [ ] Wire workflow_editor.py into main.py tray menu
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
- [ ] Add Memory Vault location wizard page to installer.iss
- [ ] Create ui/first_run.py — QWizard first-run experience
- [ ] Pages: Welcome → API Keys → Memory Vault → Voice Enrollment → Done
- [ ] Add Memory Vault path to setup_trevo.py
- [ ] Add [knowledge] section to config.toml with vault_path

### 2.8 MCP Server
- [ ] Create mcp_server/ directory
- [ ] Create mcp_server/server.py with FastMCP
- [ ] Tool: get_status (app state, engine, etc.)
- [ ] Tool: search_vault (search knowledge notes)
- [ ] Tool: trigger_workflow (run named workflow)
- [ ] Tool: get_transcript_history (query recent transcripts)
- [ ] Document Claude Remote Mode limitation (first-party only)

### 2.9 Documentation & Audit
- [ ] Create fail.md (dead code audit)
- [ ] Create PLAN.md (this file)
- [ ] Update requirements.txt with all new dependencies

### 2.10 Git & Release
- [ ] git init
- [ ] Update .gitignore (installer_output/, voices/)
- [ ] Initial commit: trevo v1.0.0
- [ ] Tag: v1.0.0
- [ ] Create GitHub repo: sidhanthbibi/trevo
- [ ] Push to GitHub

---

## Phase 3: Future (Not Started)

### Cross-Platform
- [ ] macOS support (replace pywin32, test PyInstaller on Mac)
- [ ] Linux support (PulseAudio/PipeWire, .deb/.AppImage packaging)
- [ ] Mobile companion app (React Native or Flutter)

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
