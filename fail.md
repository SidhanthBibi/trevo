# trevo — Failure & Dead Code Audit

> Generated: 2026-03-23 | Updated: 2026-03-23
> Audit of all integration gaps, dead code, known bugs, and security issues

---

## FIXED: Critical Issues (Resolved)

### 1. `ui/workflow_editor.py` — BROKEN import path
- **Was**: `from trevo.core.workflow_engine import ...` (line 78, 601)
- **Issue**: Project uses bare `from core.xxx` imports, not `from trevo.core`
- **Fix**: Changed to `from core.workflow_engine import ...`
- **Status**: FIXED

### 2. `ui/workflow_editor.py` — asyncio.run blocks Qt event loop
- **Was**: `asyncio.run(_run())` in `_run_workflow()` (line 1173-1177)
- **Issue**: Blocks entire Qt GUI until workflow completes
- **Fix**: Moved to background thread with `threading.Thread`
- **Status**: FIXED

### 3. `ui/trevo_mode.py` — glPointSize inside glBegin/glEnd
- **Was**: `glPointSize(size)` called between `glBegin(GL_POINTS)` and `glEnd()` (line 324)
- **Issue**: OpenGL spec violation, silently ignored, all particles same size
- **Fix**: Each particle now has its own `glBegin/glEnd` pair with `glPointSize` before `glBegin`
- **Status**: FIXED

### 4. `ui/settings_dialog.py` — Gemini/Google Cloud keys lost on save
- **Was**: `get_settings()` didn't include `gemini_stt_api_key` or `google_cloud_stt_api_key`
- **Issue**: Keys entered by user silently discarded
- **Fix**: Added both keys to `get_settings()` and `_load_settings()`
- **Status**: FIXED

### 5. `ui/settings_dialog.py` — Engine change handler not triggered on load
- **Was**: `_on_engine_changed` only fires on `currentIndexChanged`, missed when default already selected
- **Fix**: Added manual `_on_engine_changed()` call after setting engine index in `_load_settings()`
- **Status**: FIXED

### 6. `main.py` — Settings dialog opens with defaults, never persists
- **Was**: `SettingsDialog(parent=None)` with no current settings passed
- **Issue**: Dialog always showed defaults. Changes were logged but never saved.
- **Fix**: Now passes current settings dict and writes changes back via `settings.save()`
- **Status**: FIXED

### 7. `main.py` — Double-prefixed tray menu text
- **Was**: `tray.set_engine_status(f"Engine: {engine_name}")` but tray adds its own "Engine: " prefix
- **Result**: Menu showed "Engine: Engine: groq"
- **Fix**: Removed redundant prefix from `main.py`
- **Status**: FIXED

### 8. `ui/dictation_bar.py` — _ui_font never tries fallback fonts
- **Was**: `for family in (...):` loop returned on first iteration unconditionally
- **Fix**: Added `QFontDatabase.families()` check before returning
- **Status**: FIXED

### 9. `core/desktop_automation.py` — Command injection via shell=True
- **Was**: `subprocess.Popen(executable, shell=True)` with user-provided app name falling through to raw string
- **Issue**: If app_name not in aliases, raw string passed to shell — potential command injection
- **Fix**: Only known aliases accepted, unknown apps rejected. Removed `shell=True`, use list args.
- **Status**: FIXED (Security)

### 10. `core/workflow_engine.py` — exec() with no builtins still unsafe
- **Was**: `exec(code, {"__builtins__": {}}, ...)` — empty builtins
- **Issue**: Empty dict still allows some introspection attacks
- **Fix**: Replaced with explicit safe_builtins whitelist (len, str, int, etc.)
- **Status**: FIXED (Security)

---

## FIXED: Dead Code (Previously not wired in, now integrated)

### 11. `core/stt_gemini.py` — Now wired into app.py
- **Status**: FIXED — Gemini STT engine available in dropdown

### 12. `core/stt_google.py` — Now wired into app.py
- **Status**: FIXED — Google Cloud STT available, encoding mismatch fixed

### 13. `core/agent_mode.py` — Now wired into main.py
- **Status**: FIXED — Agent orchestrator initialized

### 14. `core/workflow_engine.py` — Now wired via workflow_editor
- **Status**: FIXED — Accessible from tray menu

### 15. `ui/workflow_editor.py` — Now accessible from tray menu
- **Status**: FIXED — "Workflow Editor" menu item added

---

## REMAINING: Known Issues

### 16. Workflow engine placeholder executors
- **Severity**: MEDIUM
- **Issue**: STTExecutor, LLMExecutor, TextInjectExecutor, AudioInputExecutor return dummy values
- **Impact**: Workflows run but produce no real output
- **Fix needed**: Connect executors to real core modules

### 17. Smart Assistant preset race condition
- **Issue**: Both `llm` and `polish` outputs connect to same `inject` input — last writer wins
- **Fix needed**: Add Merge node between them

### 18. Settings dialog flat dict → Settings dataclass mapping
- **Severity**: LOW
- **Issue**: Dialog uses flat keys, app uses nested dataclass. Translation is minimal.
- **Impact**: Some settings may not fully persist across all fields
- **Fix needed**: Complete bidirectional mapping in main.py

### 19. Morning briefing workflow is stubbed
- **Severity**: LOW
- **Issue**: "Wake up daddy's home" is detected but only shows sphere — no news/weather/tabs
- **Fix needed**: Implement RSS fetch, weather API, browser tab opening

### 20. `core/desktop_automation.py` — run_system_command uses shell=True
- **Severity**: MEDIUM (mitigated by whitelist + confirmation flow)
- **Issue**: `run_system_command()` and `run_system_command_confirmed()` still use `shell=True`
- **Mitigation**: Whitelist check + user confirmation required for non-whitelisted commands
- **Fix needed**: Parse commands into list args where possible

### 21. API keys stored in plaintext config.toml
- **Severity**: LOW (local file, in .gitignore)
- **Fix needed**: Windows Credential Store integration (Phase 3)

---

## NOT A BUG: Intentional Design

### Python 3.14 compatibility
- **Status**: Known — torch/faster-whisper may not have wheels. Recommended Python 3.11-3.12.

### No remote telemetry
- **Status**: Intentional — trevo collects zero analytics. All data stays local.
