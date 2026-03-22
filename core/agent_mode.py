"""Phase 2 Agent Mode for trevo.

Receives voice commands and routes them to different AI providers
based on task complexity:

- **Simple tasks** (text generation, emails, formatting, translation)
  are routed to Groq (fast, free tier).
- **Agentic tasks** (app orchestration, file operations, desktop
  automation, multi-step reasoning) are routed to Claude via the
  ``claude`` CLI (subscription-based, NOT API key).
- The user can explicitly say "use Claude" or "use Groq" to override.

Claude integration uses ``claude --print`` mode for non-interactive
output, spawning the CLI as a subprocess.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from utils.logger import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Provider(str, Enum):
    """Available AI providers."""
    GROQ = "groq"
    CLAUDE_CLI = "claude_cli"
    LOCAL = "local"  # Regex/heuristic only, no LLM call


class TaskComplexity(str, Enum):
    """Complexity classification for routing decisions."""
    SIMPLE = "simple"
    AGENTIC = "agentic"
    DESKTOP = "desktop"     # Desktop automation (handled locally)
    AMBIGUOUS = "ambiguous"


@dataclass
class ExecutionStep:
    """A single step in a multi-step agent execution."""
    action: str
    description: str
    result: str = ""
    success: bool = True
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentResult:
    """Result returned by the Agent Orchestrator.

    Attributes
    ----------
    action : str
        What the caller should do:
        - ``"inject_text"``: paste text into active field
        - ``"execute"``: a desktop operation was performed
        - ``"confirm"``: needs user confirmation before proceeding
        - ``"error"``: something went wrong
    text : str
        The generated text or operation summary.
    provider_used : str
        Which provider handled the request.
    execution_steps : list[ExecutionStep]
        Audit trail of steps taken.
    requires_confirmation : bool
        If True, caller should confirm before committing.
    confirmation_data : dict
        Data needed to execute after confirmation.
    error : str
        Error message if action is ``"error"``.
    """
    action: str = "inject_text"
    text: str = ""
    provider_used: str = ""
    execution_steps: list[ExecutionStep] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# Task classification patterns
# ---------------------------------------------------------------------------

# Desktop automation patterns — matched first, handled locally
_DESKTOP_PATTERNS: list[tuple[re.Pattern[str], str, list[str]]] = [
    # Open apps
    (re.compile(r"(?:open|launch|start|run)\s+(.+)", re.I), "open_app", ["app_name"]),

    # File operations
    (re.compile(r"create\s+(?:a\s+)?file\s+(?:called|named)\s+(.+?)(?:\s+(?:with|containing)\s+(.+))?$", re.I), "create_file", ["filename", "content"]),
    (re.compile(r"(?:read|show|display|cat)\s+(?:the\s+)?file\s+(.+)", re.I), "read_file", ["filename"]),
    (re.compile(r"(?:find|search\s+for|list)\s+files?\s+(?:named|matching|called)\s+(.+?)(?:\s+in\s+(.+))?$", re.I), "find_files", ["pattern", "directory"]),
    (re.compile(r"list\s+(?:the\s+)?files?\s+in\s+(.+)", re.I), "list_files", ["directory"]),
    (re.compile(r"delete\s+(?:the\s+)?file\s+(.+)", re.I), "delete_file", ["filename"]),

    # Window management
    (re.compile(r"(?:switch\s+to|focus|go\s+to)\s+(.+)", re.I), "focus_window", ["window"]),
    (re.compile(r"minimize\s+(.+)", re.I), "minimize_window", ["window"]),
    (re.compile(r"(?:list|show)\s+(?:all\s+)?(?:open\s+)?windows", re.I), "list_windows", []),

    # System queries
    (re.compile(r"what(?:'s| is)\s+my\s+(?:ip|ip\s*address)", re.I), "get_ip", []),
    (re.compile(r"(?:how\s+much\s+)?(?:disk|storage|drive)\s*(?:space|left|available|usage)?", re.I), "disk_space", []),
    (re.compile(r"(?:how\s+much\s+)?(?:ram|memory)\s*(?:left|available|usage|used)?", re.I), "system_info", []),
    (re.compile(r"(?:battery|power)\s*(?:level|status|left|percentage)?", re.I), "system_info", []),
    (re.compile(r"system\s+(?:info|information|status|stats)", re.I), "system_info", []),

    # Clipboard
    (re.compile(r"(?:copy|put)\s+(?:this|that|it)\s+(?:to|in|on)\s+(?:the\s+)?clipboard", re.I), "copy_clipboard", []),
    (re.compile(r"(?:what(?:'s| is)|show)\s+(?:on|in)\s+(?:the\s+)?clipboard", re.I), "get_clipboard", []),
    (re.compile(r"(?:paste|get)\s+(?:from\s+)?(?:the\s+)?clipboard", re.I), "get_clipboard", []),

    # Run command
    (re.compile(r"(?:run|execute)\s+(?:the\s+)?(?:command\s+)?(.+)", re.I), "run_command", ["command"]),

    # App-specific actions
    (re.compile(r"in\s+(?:vs\s*code|vscode),?\s+(.+)", re.I), "vscode_action", ["action"]),
]

# Patterns that indicate a simple/text-generation task (route to Groq)
_SIMPLE_TASK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:write|draft|compose)\s+(?:me\s+)?(?:a|an)\s+(?:email|message|letter|reply|response)", re.I),
    re.compile(r"(?:translate|convert)\s+.+\s+(?:to|into)\s+\w+", re.I),
    re.compile(r"(?:summarize|summarise)\s+", re.I),
    re.compile(r"(?:explain|describe|define)\s+", re.I),
    re.compile(r"(?:make|rewrite|rephrase)\s+(?:this|it|that)\s+", re.I),
    re.compile(r"(?:fix|correct|improve)\s+(?:the\s+)?(?:grammar|spelling|writing|text)", re.I),
    re.compile(r"(?:generate|create|give\s+me)\s+(?:a\s+)?(?:list|summary|outline|draft|template)", re.I),
    re.compile(r"(?:how\s+do\s+(?:I|you)|what\s+is|what\s+are|who\s+is|when\s+was)", re.I),
    re.compile(r"(?:format|style)\s+(?:this|it|that)\s+(?:as|like|into)", re.I),
]

# Patterns that indicate an agentic task (route to Claude CLI)
_AGENTIC_TASK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:build|create|make|set\s*up)\s+(?:a|an|the)\s+(?:project|app|application|website|script|tool)", re.I),
    re.compile(r"(?:debug|investigate|figure\s+out|analyze|diagnose)\s+", re.I),
    re.compile(r"(?:refactor|restructure|reorganize)\s+", re.I),
    re.compile(r"(?:review|audit)\s+(?:the\s+)?(?:code|project|codebase)", re.I),
    re.compile(r"(?:write|create|add)\s+(?:the\s+)?(?:tests?|unit\s+tests?)", re.I),
    re.compile(r"(?:plan|design|architect)\s+", re.I),
    re.compile(r"multi[- ]?step|step[- ]by[- ]step|complex\s+task", re.I),
    re.compile(r"(?:read|look\s+at|check|examine)\s+(?:the\s+)?(?:code|file|project|repo)", re.I),
    re.compile(r"(?:implement|add\s+(?:a\s+)?feature|integrate)", re.I),
]

# Explicit provider override patterns
_USE_CLAUDE_PATTERN = re.compile(
    r"(?:use|with|via|through)\s+claude\b", re.I,
)
_USE_GROQ_PATTERN = re.compile(
    r"(?:use|with|via|through)\s+groq\b", re.I,
)


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------

@dataclass
class AgentMemory:
    """Tracks context across agent interactions.

    Remembers what apps are open, what files were mentioned,
    and maintains a rolling conversation history.
    """
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    open_apps: list[str] = field(default_factory=list)
    mentioned_files: list[str] = field(default_factory=list)
    mentioned_directories: list[str] = field(default_factory=list)
    last_command: str = ""
    last_result: str = ""
    max_history: int = 20

    def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        # Trim old history
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

    def track_app(self, app_name: str) -> None:
        """Record that an app was opened."""
        if app_name not in self.open_apps:
            self.open_apps.append(app_name)

    def track_file(self, file_path: str) -> None:
        """Record that a file was mentioned or operated on."""
        if file_path not in self.mentioned_files:
            self.mentioned_files.append(file_path)
            # Keep only recent files
            if len(self.mentioned_files) > 50:
                self.mentioned_files = self.mentioned_files[-50:]

    def get_context_summary(self) -> str:
        """Build a summary string for LLM context injection."""
        parts: list[str] = []
        if self.open_apps:
            parts.append(f"Open apps: {', '.join(self.open_apps[-5:])}")
        if self.mentioned_files:
            parts.append(f"Recent files: {', '.join(self.mentioned_files[-5:])}")
        if self.last_command:
            parts.append(f"Last command: {self.last_command}")
        if self.last_result:
            # Truncate long results
            truncated = self.last_result[:200]
            if len(self.last_result) > 200:
                truncated += "..."
            parts.append(f"Last result: {truncated}")
        return "\n".join(parts)

    def clear(self) -> None:
        """Reset all memory."""
        self.conversation_history.clear()
        self.open_apps.clear()
        self.mentioned_files.clear()
        self.mentioned_directories.clear()
        self.last_command = ""
        self.last_result = ""


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """A single entry in the agent audit log."""
    timestamp: datetime
    command: str
    provider: str
    action: str
    success: bool
    details: str = ""


class AuditLog:
    """Append-only log of all agent actions for transparency."""

    def __init__(self, max_entries: int = 500) -> None:
        self._entries: list[AuditEntry] = []
        self._max = max_entries

    def log(
        self,
        command: str,
        provider: str,
        action: str,
        success: bool,
        details: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=datetime.now(),
            command=command,
            provider=provider,
            action=action,
            success=success,
            details=details,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

        logger.debug(
            "AUDIT | provider={} action={} success={} | {}",
            provider, action, success, details[:120],
        )

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    @property
    def recent(self) -> list[AuditEntry]:
        return self._entries[-10:]


# ---------------------------------------------------------------------------
# AgentOrchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    """Phase 2 Agent Mode orchestrator for trevo.

    Receives voice commands, classifies their complexity, and routes
    them to the appropriate provider:

    - **Local** — desktop automation (open apps, file ops, system queries)
    - **Groq** — simple text tasks (fast, free tier)
    - **Claude CLI** — agentic tasks (multi-step reasoning, code generation)

    Parameters
    ----------
    provider_config : dict
        Configuration dict with keys:

        - ``groq_api_key`` (str): Groq API key for simple tasks
        - ``groq_model`` (str, optional): Model override (default: llama-3.3-70b-versatile)
        - ``claude_cli_path`` (str, optional): Path to claude CLI binary
        - ``default_provider`` (str, optional): Default provider override
        - ``confirm_destructive`` (bool, optional): Whether to confirm destructive ops (default: True)
    """

    def __init__(self, provider_config: dict[str, Any]) -> None:
        self._config = provider_config
        self._groq_key = provider_config.get("groq_api_key", "")
        self._groq_model = provider_config.get("groq_model", "llama-3.3-70b-versatile")
        self._claude_cli = provider_config.get("claude_cli_path", "claude")
        self._confirm_destructive = provider_config.get("confirm_destructive", True)

        self._memory = AgentMemory()
        self._audit = AuditLog()

        # Pending confirmations (keyed by a simple counter)
        self._pending_confirmations: dict[int, dict[str, Any]] = {}
        self._confirmation_counter = 0

        logger.info(
            "AgentOrchestrator initialised (groq_key={}, claude_cli={})",
            "set" if self._groq_key else "unset",
            self._claude_cli,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> AgentMemory:
        """Access the conversation memory."""
        return self._memory

    @property
    def audit_log(self) -> AuditLog:
        """Access the audit log."""
        return self._audit

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_agent_command(self, text: str) -> AgentResult:
        """Process a voice command through the agent pipeline.

        Parameters
        ----------
        text : str
            The transcribed voice command.

        Returns
        -------
        AgentResult
            The result with action, text, provider info, and execution steps.
        """
        if not text or not text.strip():
            return AgentResult(action="error", error="Empty command")

        command = text.strip()
        self._memory.add_turn("user", command)
        self._memory.last_command = command

        logger.info("Agent command: '{}'", command[:120])

        steps: list[ExecutionStep] = []

        # Step 1: Check for explicit provider override
        forced_provider = self._detect_provider_override(command)
        if forced_provider:
            command = self._strip_provider_override(command)
            steps.append(ExecutionStep(
                action="provider_override",
                description=f"User requested provider: {forced_provider.value}",
            ))

        # Step 2: Check for desktop automation patterns (handled locally)
        desktop_match = self._match_desktop_pattern(command)
        if desktop_match and forced_provider is None:
            steps.append(ExecutionStep(
                action="classify",
                description="Classified as desktop automation task",
            ))
            result = await self._execute_desktop_action(desktop_match, steps)
            self._audit.log(command, "local", desktop_match["action"], result.action != "error")
            self._memory.last_result = result.text
            return result

        # Step 3: Classify task complexity
        if forced_provider:
            provider = forced_provider
        else:
            complexity = self._classify_task(command)
            steps.append(ExecutionStep(
                action="classify",
                description=f"Task complexity: {complexity.value}",
            ))
            provider = self._route_to_provider(complexity)

        steps.append(ExecutionStep(
            action="route",
            description=f"Routing to provider: {provider.value}",
        ))

        # Step 4: Execute with the chosen provider
        if provider == Provider.GROQ:
            result = await self._execute_groq(command, steps)
        elif provider == Provider.CLAUDE_CLI:
            result = await self._execute_claude_cli(command, steps)
        else:
            result = AgentResult(
                action="error",
                error="No suitable provider available",
                execution_steps=steps,
            )

        self._audit.log(
            command, provider.value, result.action,
            result.action != "error",
            details=result.text[:200] if result.text else result.error,
        )
        self._memory.last_result = result.text or result.error
        self._memory.add_turn("assistant", result.text or result.error)

        return result

    async def confirm_pending(self, confirmation_id: int) -> AgentResult:
        """Execute a previously pending operation after user confirmation.

        Parameters
        ----------
        confirmation_id : int
            The ID returned in ``confirmation_data["id"]`` of the original result.

        Returns
        -------
        AgentResult
            The result of the confirmed operation.
        """
        pending = self._pending_confirmations.pop(confirmation_id, None)
        if pending is None:
            return AgentResult(
                action="error",
                error=f"No pending confirmation with id {confirmation_id}",
            )

        action = pending["action"]
        logger.info("Executing confirmed action: {}", action)

        from core.desktop_automation import (
            create_file_force,
            delete_file_confirmed,
            run_system_command_confirmed,
        )

        if action == "overwrite":
            result = create_file_force(pending["path"], pending.get("content", ""))
        elif action == "delete":
            result = delete_file_confirmed(pending["path"])
        elif action == "run_command":
            result = run_system_command_confirmed(pending["command"])
        else:
            return AgentResult(action="error", error=f"Unknown confirmation action: {action}")

        self._audit.log(
            f"confirmed:{action}", "local", action,
            result.success, result.output or result.error,
        )

        return AgentResult(
            action="execute" if result.success else "error",
            text=result.output,
            provider_used="local",
            error=result.error,
        )

    def reset_memory(self) -> None:
        """Clear all conversation memory and pending confirmations."""
        self._memory.clear()
        self._pending_confirmations.clear()
        logger.info("Agent memory cleared")

    # ------------------------------------------------------------------
    # Provider override detection
    # ------------------------------------------------------------------

    def _detect_provider_override(self, text: str) -> Optional[Provider]:
        """Check if the user explicitly requested a provider."""
        if _USE_CLAUDE_PATTERN.search(text):
            return Provider.CLAUDE_CLI
        if _USE_GROQ_PATTERN.search(text):
            return Provider.GROQ
        return None

    def _strip_provider_override(self, text: str) -> str:
        """Remove the provider override phrase from the command text."""
        text = _USE_CLAUDE_PATTERN.sub("", text).strip()
        text = _USE_GROQ_PATTERN.sub("", text).strip()
        # Clean up leftover commas/dashes
        text = re.sub(r"^[\s,\-]+", "", text)
        return text

    # ------------------------------------------------------------------
    # Task classification
    # ------------------------------------------------------------------

    def _classify_task(self, text: str) -> TaskComplexity:
        """Classify task complexity using local regex patterns.

        Falls back to AMBIGUOUS if no pattern matches — caller
        will then use Groq to disambiguate.
        """
        # Desktop patterns already handled upstream, but double-check
        for pattern, action, _ in _DESKTOP_PATTERNS:
            if pattern.search(text):
                return TaskComplexity.DESKTOP

        # Check simple patterns
        for pattern in _SIMPLE_TASK_PATTERNS:
            if pattern.search(text):
                return TaskComplexity.SIMPLE

        # Check agentic patterns
        for pattern in _AGENTIC_TASK_PATTERNS:
            if pattern.search(text):
                return TaskComplexity.AGENTIC

        return TaskComplexity.AMBIGUOUS

    def _route_to_provider(self, complexity: TaskComplexity) -> Provider:
        """Map complexity to a provider."""
        if complexity == TaskComplexity.DESKTOP:
            return Provider.LOCAL
        if complexity == TaskComplexity.SIMPLE:
            if self._groq_key:
                return Provider.GROQ
            # Fallback to Claude CLI if no Groq key
            return Provider.CLAUDE_CLI
        if complexity == TaskComplexity.AGENTIC:
            return Provider.CLAUDE_CLI
        # AMBIGUOUS — default to Groq for speed, unless we have no key
        if self._groq_key:
            return Provider.GROQ
        return Provider.CLAUDE_CLI

    # ------------------------------------------------------------------
    # Desktop automation execution
    # ------------------------------------------------------------------

    def _match_desktop_pattern(self, text: str) -> Optional[dict[str, Any]]:
        """Try to match text against desktop automation patterns."""
        for pattern, action, param_names in _DESKTOP_PATTERNS:
            match = pattern.search(text)
            if match:
                params: dict[str, Any] = {"action": action}
                for i, name in enumerate(param_names):
                    try:
                        value = match.group(i + 1)
                        if value is not None:
                            params[name] = value.strip()
                    except IndexError:
                        pass
                return params
        return None

    async def _execute_desktop_action(
        self, match: dict[str, Any], steps: list[ExecutionStep],
    ) -> AgentResult:
        """Execute a desktop automation action."""
        from core import desktop_automation as da

        action = match["action"]
        logger.info("Desktop action: {} params={}", action, match)

        try:
            if action == "open_app":
                app_name = match.get("app_name", "")
                result = da.open_application(app_name)
                self._memory.track_app(app_name)

            elif action == "create_file":
                filename = match.get("filename", "")
                content = match.get("content", "")
                result = da.create_file(filename, content)
                if result.success:
                    self._memory.track_file(filename)

            elif action == "read_file":
                filename = match.get("filename", "")
                result = da.read_file(filename)
                self._memory.track_file(filename)

            elif action == "find_files" or action == "list_files":
                pattern = match.get("pattern", "*")
                directory = match.get("directory", ".")
                result = da.list_files(directory, pattern, recursive=True)

            elif action == "delete_file":
                filename = match.get("filename", "")
                result = da.delete_file(filename)

            elif action == "focus_window":
                window = match.get("window", "")
                result = da.focus_window(window)

            elif action == "minimize_window":
                window = match.get("window", "")
                result = da.minimize_window(window if window else None)

            elif action == "list_windows":
                result = da.list_windows()

            elif action == "get_ip":
                result = da.get_ip_address()

            elif action == "disk_space":
                result = da.get_disk_space()

            elif action == "system_info":
                result = da.get_system_info()

            elif action == "get_clipboard":
                result = da.get_clipboard()

            elif action == "copy_clipboard":
                # Copy last result or draft to clipboard
                text_to_copy = self._memory.last_result or ""
                result = da.set_clipboard(text_to_copy)

            elif action == "run_command":
                command = match.get("command", "")
                result = da.run_system_command(command)

            elif action == "vscode_action":
                # Route VS Code specific actions through Claude CLI
                vscode_cmd = match.get("action", "")
                return await self._execute_claude_cli(
                    f"In VS Code, {vscode_cmd}", steps,
                )

            else:
                return AgentResult(
                    action="error",
                    error=f"Unknown desktop action: {action}",
                    provider_used="local",
                    execution_steps=steps,
                )

            steps.append(ExecutionStep(
                action=action,
                description=f"Executed: {action}",
                result=result.output[:200] if result.output else result.error,
                success=result.success,
            ))

            # Handle confirmation-required results
            if result.requires_confirmation and self._confirm_destructive:
                self._confirmation_counter += 1
                cid = self._confirmation_counter
                self._pending_confirmations[cid] = {
                    **result.metadata,
                    "action": result.metadata.get("action", action),
                }
                return AgentResult(
                    action="confirm",
                    text=result.output or result.error,
                    provider_used="local",
                    execution_steps=steps,
                    requires_confirmation=True,
                    confirmation_data={"id": cid, **result.metadata},
                )

            return AgentResult(
                action="execute" if result.success else "error",
                text=result.output,
                provider_used="local",
                execution_steps=steps,
                error=result.error,
            )

        except Exception as e:
            logger.exception("Desktop action failed: {}", action)
            steps.append(ExecutionStep(
                action=action,
                description=f"Failed: {e}",
                success=False,
            ))
            return AgentResult(
                action="error",
                error=str(e),
                provider_used="local",
                execution_steps=steps,
            )

    # ------------------------------------------------------------------
    # Groq execution
    # ------------------------------------------------------------------

    async def _execute_groq(
        self, command: str, steps: list[ExecutionStep],
    ) -> AgentResult:
        """Send a simple task to Groq for fast inference."""
        if not self._groq_key:
            steps.append(ExecutionStep(
                action="groq_fallback",
                description="No Groq API key — falling back to Claude CLI",
            ))
            return await self._execute_claude_cli(command, steps)

        logger.info("Executing via Groq (model={})", self._groq_model)

        # Build prompt with conversation context
        system_prompt = (
            "You are a helpful assistant integrated into a voice-controlled desktop app called trevo. "
            "The user gives you voice commands. Respond concisely and directly. "
            "If the user asks you to write or generate text, return ONLY the text they asked for, "
            "no commentary or meta-text."
        )

        context = self._memory.get_context_summary()
        if context:
            system_prompt += f"\n\nCurrent context:\n{context}"

        try:
            import openai

            client = openai.AsyncOpenAI(
                api_key=self._groq_key,
                base_url="https://api.groq.com/openai/v1",
            )

            # Build message history from memory
            messages: list[dict[str, str]] = [
                {"role": "system", "content": system_prompt},
            ]
            # Include recent conversation turns for continuity
            for turn in self._memory.conversation_history[-6:]:
                messages.append({
                    "role": turn["role"] if turn["role"] in ("user", "assistant") else "user",
                    "content": turn["content"],
                })
            # Ensure the current command is the last user message
            if not messages or messages[-1].get("content") != command:
                messages.append({"role": "user", "content": command})

            response = await client.chat.completions.create(
                model=self._groq_model,
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )

            result_text = response.choices[0].message.content.strip()

            steps.append(ExecutionStep(
                action="groq_inference",
                description=f"Groq {self._groq_model} responded",
                result=result_text[:200],
                success=True,
            ))

            return AgentResult(
                action="inject_text",
                text=result_text,
                provider_used=f"groq:{self._groq_model}",
                execution_steps=steps,
            )

        except ImportError:
            logger.error("openai package not installed — cannot use Groq")
            return AgentResult(
                action="error",
                error="openai package required for Groq. Run: pip install openai",
                execution_steps=steps,
            )
        except Exception as e:
            logger.exception("Groq inference failed")
            steps.append(ExecutionStep(
                action="groq_error",
                description=f"Groq failed: {e}",
                success=False,
            ))
            # Fallback to Claude CLI
            steps.append(ExecutionStep(
                action="fallback",
                description="Falling back to Claude CLI",
            ))
            return await self._execute_claude_cli(command, steps)

    # ------------------------------------------------------------------
    # Claude CLI execution
    # ------------------------------------------------------------------

    async def _execute_claude_cli(
        self, command: str, steps: list[ExecutionStep],
    ) -> AgentResult:
        """Send an agentic task to Claude via the CLI.

        Uses ``claude --print`` mode for non-interactive output.
        The user must have a Claude subscription and the ``claude``
        CLI installed and authenticated.
        """
        logger.info("Executing via Claude CLI: '{}'", command[:120])

        # Build the full prompt with context
        context = self._memory.get_context_summary()
        full_prompt = command
        if context:
            full_prompt = (
                f"Context:\n{context}\n\n"
                f"Task: {command}"
            )

        try:
            # Run claude CLI in a subprocess
            proc = await asyncio.create_subprocess_exec(
                self._claude_cli, "--print", "-p", full_prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120.0,
            )

            result_text = stdout.decode("utf-8", errors="replace").strip()
            error_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                logger.warning(
                    "Claude CLI returned code {}: {}",
                    proc.returncode, error_text[:200],
                )
                # If claude is not installed or auth failed
                if "not found" in error_text.lower() or "not recognized" in error_text.lower():
                    steps.append(ExecutionStep(
                        action="claude_cli_error",
                        description="Claude CLI not found — is it installed?",
                        success=False,
                    ))
                    return AgentResult(
                        action="error",
                        error=(
                            "Claude CLI not found. Install it with: "
                            "npm install -g @anthropic-ai/claude-code"
                        ),
                        execution_steps=steps,
                    )

                steps.append(ExecutionStep(
                    action="claude_cli_error",
                    description=f"CLI error (code {proc.returncode}): {error_text[:200]}",
                    success=False,
                ))
                return AgentResult(
                    action="error",
                    error=error_text or f"Claude CLI exited with code {proc.returncode}",
                    provider_used="claude_cli",
                    execution_steps=steps,
                )

            steps.append(ExecutionStep(
                action="claude_cli_inference",
                description="Claude CLI responded",
                result=result_text[:200],
                success=True,
            ))

            return AgentResult(
                action="inject_text",
                text=result_text,
                provider_used="claude_cli",
                execution_steps=steps,
            )

        except asyncio.TimeoutError:
            logger.error("Claude CLI timed out after 120s")
            steps.append(ExecutionStep(
                action="claude_cli_timeout",
                description="Claude CLI timed out after 120 seconds",
                success=False,
            ))
            return AgentResult(
                action="error",
                error="Claude CLI timed out after 120 seconds",
                provider_used="claude_cli",
                execution_steps=steps,
            )
        except FileNotFoundError:
            logger.error("Claude CLI binary not found at: {}", self._claude_cli)
            steps.append(ExecutionStep(
                action="claude_cli_not_found",
                description=f"Binary not found: {self._claude_cli}",
                success=False,
            ))
            return AgentResult(
                action="error",
                error=(
                    f"Claude CLI not found at '{self._claude_cli}'. "
                    "Install with: npm install -g @anthropic-ai/claude-code"
                ),
                provider_used="claude_cli",
                execution_steps=steps,
            )
        except Exception as e:
            logger.exception("Claude CLI execution failed")
            steps.append(ExecutionStep(
                action="claude_cli_error",
                description=f"Unexpected error: {e}",
                success=False,
            ))
            return AgentResult(
                action="error",
                error=str(e),
                provider_used="claude_cli",
                execution_steps=steps,
            )
