# trevo — Failure & Dead Code Audit

> Generated: 2026-03-23 | Audit of all integration gaps, dead code, and known bugs

---

## CRITICAL: Dead Code (Built but never wired in)

### 1. `core/stt_gemini.py` — Gemini STT Engine
- **Status**: DEAD CODE
- **Severity**: HIGH
- **Issue**: Complete implementation exists but `core/app.py:_create_stt_engine()` has no `"gemini"` branch
- **Bug**: Line with `_ENDPOINT` hardcodes `gemini-2.0-flash` in the URL instead of using `self._model`
- **Fix**: Add `if engine_name == "gemini":` in app.py, fix URL to use `self._model`

### 2. `core/stt_google.py` — Google Cloud STT Engine
- **Status**: DEAD CODE
- **Severity**: HIGH
- **Issue**: Complete implementation exists but `core/app.py:_create_stt_engine()` has no `"google_cloud"` branch
- **Bug**: Sends WAV-wrapped audio but declares `encoding: LINEAR16` (expects raw PCM). API may reject or mishandle.
- **Fix**: Add `if engine_name == "google_cloud":` in app.py, send raw PCM instead of WAV wrapper

### 3. `core/agent_mode.py` — Agent Orchestrator (Phase 2)
- **Status**: DEAD CODE
- **Severity**: MEDIUM
- **Issue**: 933-line file with full routing, desktop automation, audit logs. Never imported by app.py. Listed in build.py hidden imports but unreachable at runtime.
- **Security**: `desktop_automation.py:open_application()` uses `shell=True` with user input — potential command injection if app_name bypasses alias lookup
- **Fix**: Import and initialize in app.py, add AGENT_MODE state, sanitize shell inputs

### 4. `core/desktop_automation.py` — Desktop Operations
- **Status**: DEAD CODE (only imported by dead agent_mode.py)
- **Severity**: MEDIUM
- **Issue**: Complete safe wrappers for file ops, clipboard, window management, system queries. Unreachable because agent_mode.py is itself dead.
- **Fix**: Will become reachable once agent_mode is wired in

### 5. `core/workflow_engine.py` — Workflow Engine
- **Status**: DEAD CODE
- **Severity**: HIGH
- **Issue**: Full workflow data model with 15 node types, topological sort execution, JSON save/load. Never imported or used.
- **Bug**: Node executors are ALL PLACEHOLDERS — `AudioInputExecutor`, `STTExecutor`, `LLMExecutor`, `TextInjectExecutor` return hardcoded dummy values instead of calling real modules.
- **Bug**: Smart Assistant preset connects both `llm` and `polish` outputs to same `inject` input — race condition, last writer wins.
- **Fix**: Wire into main.py, connect executors to real modules, fix preset

### 6. `ui/workflow_editor.py` — Visual Node Editor UI
- **Status**: DEAD CODE
- **Severity**: HIGH
- **Issue**: 1100+ lines of PyQt6 node canvas (nodes, connections, palette, properties panel). Never instantiated in main.py. No menu item or hotkey triggers it.
- **Fix**: Add "Workflow Editor" to tray menu, import and open WorkflowEditorDialog

---

## MEDIUM: Config & Settings Mismatches

### 7. `config.toml` out of sync with `config.toml.example`
- **Issue**: config.toml missing `groq_api_key = ""` under `[stt]` section
- **Issue**: Engine comment says `"deepgram", "whisper_local", "openai"` — missing `"groq"`, `"gemini"`, `"google_cloud"`
- **Fix**: Add missing fields, update comments

### 8. `models/settings.py` missing `gemini_api_key` in STTSettings
- **Issue**: `STTSettings` has `groq_api_key` but no `gemini_api_key`. If someone sets `engine = "gemini"`, there's no dedicated STT key field.
- **Fix**: Add `gemini_api_key: str = ""` to STTSettings

### 9. `ui/settings_dialog.py` missing STT engine options
- **Issue**: Engine dropdown has Groq, Deepgram, Whisper, OpenAI but NOT Gemini or Google Cloud
- **Fix**: Add both as dropdown options

### 10. Settings dialog uses flat dict, not Settings dataclass
- **Issue**: `get_settings()` returns flat keys like `"stt_engine"`, `"polish_provider"` but the app uses nested `Settings.stt.engine`, `Settings.polishing.provider`. No translation layer visible.
- **Impact**: Settings saved from dialog may not properly map back to the dataclass on reload
- **Fix**: Add translation layer in main.py `_open_settings()` that maps flat dict → Settings fields

---

## LOW: Code Quality Issues

### 11. `core/app.py` unnecessary getattr calls
- **Lines**: 182, 240
- **Issue**: `getattr(self._settings.polishing, "groq_api_key", "")` is unnecessary since `groq_api_key` now exists on the dataclass
- **Fix**: Replace with direct attribute access

### 12. `core/conversation_engine.py` fragile private imports
- **Lines**: 582, 594
- **Issue**: Imports `_get_openai_client` and `_get_anthropic_client` from `core.text_polisher` — private functions, fragile coupling
- **Fix**: Make these functions public or create a shared client factory

### 13. `core/workflow_engine.py` uses stdlib logging instead of loguru
- **Issue**: Uses `logging.getLogger` while rest of codebase uses `utils.logger` (loguru)
- **Fix**: Replace with `from utils.logger import logger`

### 14. `core/agent_mode.py` dead imports
- **Lines**: 20, 22
- **Issue**: `import json` and `import subprocess` are imported but never used directly (subprocess calls use `asyncio.create_subprocess_exec`)
- **Fix**: Remove unused imports

### 15. `build.py` lists dead modules in hidden imports
- **Lines**: 86-87
- **Issue**: `core.agent_mode` and `core.desktop_automation` are in hidden imports but never imported at runtime
- **Impact**: Increases exe size with dead code
- **Fix**: Keep them (they'll be wired in Phase 2) but add new missing modules too

---

## NOT A BUG: Intentional Design

### No git repository
- **Status**: Expected — project was being built, git init is part of Phase 2 release

### API keys in plaintext config.toml
- **Status**: Acceptable — config.toml is in .gitignore, local-only file. Windows credential store integration would be Phase 3.

### Python 3.14 compatibility
- **Status**: Known — torch/faster-whisper may not have wheels. Recommended Python 3.11-3.12.
