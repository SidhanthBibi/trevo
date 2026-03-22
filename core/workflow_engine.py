"""Node-based workflow engine for trevo.

Provides the data model, built-in node executors, and an async execution
engine that topologically sorts a directed acyclic graph of nodes and
streams data through connected ports.

Inspired by DaVinci Resolve's node compositor -- each node is a box with
typed input/output ports, connected by wires.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.logger import logger as log

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

PORT_TYPES: set[str] = {"text", "audio", "any", "bool", "number", "results"}


@dataclass
class Port:
    """Input or output port on a node."""

    name: str
    port_type: str  # "text", "audio", "any", "bool", "number", "results"
    direction: str  # "input" or "output"
    connected_to: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.port_type not in PORT_TYPES:
            raise ValueError(
                f"Invalid port type {self.port_type!r}. "
                f"Must be one of {PORT_TYPES}"
            )
        if self.direction not in ("input", "output"):
            raise ValueError(
                f"Invalid direction {self.direction!r}. "
                "Must be 'input' or 'output'"
            )


@dataclass
class WorkflowNode:
    """A single node in the workflow graph."""

    id: str
    node_type: str
    label: str
    config: dict[str, Any]
    inputs: list[Port]
    outputs: list[Port]
    position: tuple[float, float] = (0.0, 0.0)

    # ---- helpers ----------------------------------------------------------

    def input_port(self, name: str) -> Port | None:
        """Return the input port with *name*, or ``None``."""
        return next((p for p in self.inputs if p.name == name), None)

    def output_port(self, name: str) -> Port | None:
        """Return the output port with *name*, or ``None``."""
        return next((p for p in self.outputs if p.name == name), None)


@dataclass
class WorkflowConnection:
    """A connection/wire between two ports."""

    id: str
    from_node: str
    from_port: str
    to_node: str
    to_port: str


@dataclass
class Workflow:
    """A complete workflow graph."""

    id: str
    name: str
    description: str
    nodes: dict[str, WorkflowNode]
    connections: list[WorkflowConnection]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ---- mutation helpers -------------------------------------------------

    def add_node(self, node: WorkflowNode) -> None:
        """Add *node* to the workflow."""
        self.nodes[node.id] = node
        self.updated_at = datetime.now(timezone.utc)

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its connections."""
        self.nodes.pop(node_id, None)
        self.connections = [
            c
            for c in self.connections
            if c.from_node != node_id and c.to_node != node_id
        ]
        self.updated_at = datetime.now(timezone.utc)

    def connect(
        self,
        from_node: str,
        from_port: str,
        to_node: str,
        to_port: str,
    ) -> WorkflowConnection:
        """Create a connection between two ports and return it."""
        conn = WorkflowConnection(
            id=_uid(),
            from_node=from_node,
            from_port=from_port,
            to_node=to_node,
            to_port=to_port,
        )
        self.connections.append(conn)
        # Update port bookkeeping.
        src = self.nodes[from_node].output_port(from_port)
        if src:
            src.connected_to.append((to_node, to_port))
        dst = self.nodes[to_node].input_port(to_port)
        if dst:
            dst.connected_to.append((from_node, from_port))
        self.updated_at = datetime.now(timezone.utc)
        return conn

    def disconnect(self, connection_id: str) -> None:
        """Remove a connection by id."""
        conn = next((c for c in self.connections if c.id == connection_id), None)
        if conn is None:
            return
        self.connections.remove(conn)
        src = self.nodes.get(conn.from_node)
        if src:
            p = src.output_port(conn.from_port)
            if p:
                try:
                    p.connected_to.remove((conn.to_node, conn.to_port))
                except ValueError:
                    pass
        dst = self.nodes.get(conn.to_node)
        if dst:
            p = dst.input_port(conn.to_port)
            if p:
                try:
                    p.connected_to.remove((conn.from_node, conn.from_port))
                except ValueError:
                    pass
        self.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Node executor registry
# ---------------------------------------------------------------------------

class BaseNodeExecutor(ABC):
    """Base class for all node executors.

    Subclasses implement *execute* to receive a mapping of
    ``port_name -> value`` for every connected input and return a mapping
    of ``port_name -> value`` for every output.
    """

    # Class-level metadata used by the editor.
    node_type: str = ""
    display_name: str = ""
    category: str = "Utility"
    description: str = ""
    default_config: dict[str, Any] = {}

    @staticmethod
    def default_inputs() -> list[Port]:
        """Return the default input ports for this node type."""
        return []

    @staticmethod
    def default_outputs() -> list[Port]:
        """Return the default output ports for this node type."""
        return []

    @abstractmethod
    async def execute(
        self,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the node logic.

        Args:
            inputs: Mapping of input port name to its received value.
            config: Node-specific configuration dict.

        Returns:
            Mapping of output port name to produced value.
        """
        ...


# Global registry: node_type str -> executor class
_NODE_EXECUTORS: dict[str, type[BaseNodeExecutor]] = {}


def register_node(cls: type[BaseNodeExecutor]) -> type[BaseNodeExecutor]:
    """Decorator that registers a node executor class."""
    if not cls.node_type:
        raise ValueError(f"{cls.__name__} must define a non-empty node_type")
    _NODE_EXECUTORS[cls.node_type] = cls
    return cls


def get_executor(node_type: str) -> BaseNodeExecutor:
    """Instantiate and return an executor for *node_type*."""
    cls = _NODE_EXECUTORS.get(node_type)
    if cls is None:
        raise KeyError(f"No executor registered for node type {node_type!r}")
    return cls()


def all_node_types() -> dict[str, type[BaseNodeExecutor]]:
    """Return a copy of the global executor registry."""
    return dict(_NODE_EXECUTORS)


# ---------------------------------------------------------------------------
# Built-in node executors
# ---------------------------------------------------------------------------

@register_node
class AudioInputExecutor(BaseNodeExecutor):
    """Captures microphone audio."""

    node_type = "audio_input"
    display_name = "Audio Input"
    category = "Input"
    description = "Capture audio from the system microphone."
    default_config: dict[str, Any] = {"device": "default", "sample_rate": 16000}

    @staticmethod
    def default_inputs() -> list[Port]:
        return []

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="audio", port_type="audio", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        # In a real implementation this would capture audio via the
        # project's AudioCapture module.  For now return a placeholder.
        log.info("AudioInput: capturing audio (device=%s)", config.get("device", "default"))
        return {"audio": b"<audio_placeholder>"}


@register_node
class STTExecutor(BaseNodeExecutor):
    """Speech-to-text transcription."""

    node_type = "stt"
    display_name = "Speech to Text"
    category = "AI"
    description = "Transcribe audio to text using a configurable STT engine."
    default_config: dict[str, Any] = {
        "engine": "gemini",
        "language": "en",
        "model": "",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="audio", port_type="audio", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        audio = inputs.get("audio", b"")
        engine_name = config.get("engine", "gemini")
        log.info("STT: transcribing %d bytes with engine=%s", len(audio) if isinstance(audio, bytes) else 0, engine_name)

        try:
            # Map engine names to their module and class
            _engine_map = {
                "groq": ("core.stt_groq", "GroqSTT"),
                "deepgram": ("core.stt_deepgram", "DeepgramSTTEngine"),
                "whisper_local": ("core.stt_whisper", "WhisperLocalSTT"),
                "openai": ("core.stt_openai", "OpenAISTT"),
                "gemini": ("core.stt_gemini", "GeminiSTT"),
                "google_cloud": ("core.stt_google", "GoogleCloudSTT"),
            }

            if engine_name not in _engine_map:
                log.warning("STT: unknown engine %s, falling back to placeholder", engine_name)
                return {"text": "<transcribed_text>"}

            module_path, class_name = _engine_map[engine_name]
            import importlib
            mod = importlib.import_module(module_path)
            engine_cls = getattr(mod, class_name)

            # Build kwargs from config (api_key, model, language)
            kwargs: dict[str, Any] = {}
            if config.get("api_key"):
                kwargs["api_key"] = config["api_key"]
            if config.get("model"):
                kwargs["model"] = config["model"]
            if config.get("language"):
                kwargs["language"] = config["language"]

            engine = engine_cls(**kwargs)

            # Run the streaming cycle: start -> send audio -> collect transcripts -> stop
            await engine.start_stream()
            if isinstance(audio, bytes) and audio:
                await engine.send_audio(audio)
            transcribed_parts: list[str] = []
            async for event in engine.get_transcripts():
                if event.is_final and event.text:
                    transcribed_parts.append(event.text)
            await engine.stop_stream()

            text = " ".join(transcribed_parts) if transcribed_parts else ""
            return {"text": text}

        except Exception as exc:
            log.warning("STT: engine %s failed (%s), returning placeholder", engine_name, exc)
            return {"text": "<transcribed_text>"}


@register_node
class LLMExecutor(BaseNodeExecutor):
    """Call a large language model."""

    node_type = "llm"
    display_name = "LLM"
    category = "AI"
    description = "Send text to an LLM and receive a response."
    default_config: dict[str, Any] = {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.7,
        "system_prompt": "You are a helpful assistant.",
        "max_tokens": 2048,
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = inputs.get("text", "")
        provider = config.get("provider", "groq")
        model = config.get("model", "")
        system_prompt = config.get("system_prompt", "You are a helpful assistant.")
        temperature = config.get("temperature", 0.7)
        max_tokens = config.get("max_tokens", 2048)
        api_key = config.get("api_key", "")
        log.info("LLM: provider=%s model=%s prompt_len=%d", provider, model, len(str(prompt)))

        try:
            if provider == "groq":
                import openai as _openai
                client = _openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                response = await client.chat.completions.create(
                    model=model or "llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return {"text": response.choices[0].message.content.strip()}

            elif provider == "openai":
                from core.text_polisher import _get_openai_client
                client = _get_openai_client(api_key)
                response = await client.chat.completions.create(
                    model=model or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return {"text": response.choices[0].message.content.strip()}

            elif provider == "anthropic":
                from core.text_polisher import _get_anthropic_client
                client = _get_anthropic_client(api_key)
                response = await client.messages.create(
                    model=model or "claude-3-5-haiku-20241022",
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                return {"text": response.content[0].text.strip()}

            elif provider == "ollama":
                import httpx
                ollama_url = config.get("ollama_url", "http://localhost:11434")
                url = f"{ollama_url.rstrip('/')}/api/chat"
                payload = {
                    "model": model or "llama3.2",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature},
                }
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    resp = await http_client.post(url, json=payload)
                    resp.raise_for_status()
                    return {"text": resp.json()["message"]["content"].strip()}

            elif provider == "gemini":
                import httpx
                gemini_model = model or "gemini-2.0-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
                headers = {"Content-Type": "application/json"}
                params = {"key": api_key}
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                }
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    resp = await http_client.post(url, json=payload, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return {"text": parts[0].get("text", "").strip()}
                    return {"text": ""}

            else:
                log.warning("LLM: unknown provider %s", provider)
                return {"text": f"<llm_response to: {prompt[:60]}>"}

        except Exception as exc:
            log.warning("LLM: provider %s failed (%s), returning placeholder", provider, exc)
            return {"text": f"<llm_response to: {prompt[:60]}>"}


@register_node
class TextPolishExecutor(BaseNodeExecutor):
    """Clean and format text."""

    node_type = "text_polish"
    display_name = "Text Polish"
    category = "Processing"
    description = "Clean and reformat transcribed text."
    default_config: dict[str, Any] = {
        "style": "formal",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        text = inputs.get("text", "")
        style = config.get("style", "formal")
        log.info("TextPolish: style=%s len=%d", style, len(str(text)))

        try:
            from core.text_polisher import TextPolisher

            provider = config.get("provider", "openai")
            api_key = config.get("api_key")
            model = config.get("model")
            polisher = TextPolisher(
                provider=provider,
                api_key=api_key,
                model=model,
            )
            polished = await polisher.polish(text)
            return {"text": polished}
        except Exception as exc:
            log.warning("TextPolish: polisher failed (%s), returning raw text", exc)
            return {"text": text}


@register_node
class TranslateExecutor(BaseNodeExecutor):
    """Translate text to another language."""

    node_type = "translate"
    display_name = "Translate"
    category = "AI"
    description = "Translate text to a target language."
    default_config: dict[str, Any] = {
        "target_language": "es",
        "provider": "gemini",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        text = inputs.get("text", "")
        lang = config.get("target_language", "es")
        provider = config.get("provider", "gemini")
        api_key = config.get("api_key", "")
        model = config.get("model", "")
        log.info("Translate: target=%s provider=%s len=%d", lang, provider, len(str(text)))

        translation_prompt = (
            f"Translate the following text to {lang}. "
            "Return ONLY the translated text, no commentary or explanation.\n\n"
            f"Text: {text}"
        )

        try:
            if provider == "groq":
                import openai as _openai
                client = _openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                response = await client.chat.completions.create(
                    model=model or "llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": translation_prompt}],
                    temperature=0.3,
                    max_tokens=4096,
                )
                return {"text": response.choices[0].message.content.strip()}

            elif provider == "gemini":
                import httpx
                gemini_model = model or "gemini-2.0-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
                headers = {"Content-Type": "application/json"}
                params = {"key": api_key}
                payload = {
                    "contents": [{"parts": [{"text": translation_prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
                }
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    resp = await http_client.post(url, json=payload, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return {"text": parts[0].get("text", "").strip()}
                return {"text": f"<translated:{lang}> {text}"}

            elif provider == "openai":
                from core.text_polisher import _get_openai_client
                client = _get_openai_client(api_key)
                response = await client.chat.completions.create(
                    model=model or "gpt-4o-mini",
                    messages=[{"role": "user", "content": translation_prompt}],
                    temperature=0.3,
                    max_tokens=4096,
                )
                return {"text": response.choices[0].message.content.strip()}

            elif provider == "anthropic":
                from core.text_polisher import _get_anthropic_client
                client = _get_anthropic_client(api_key)
                response = await client.messages.create(
                    model=model or "claude-3-5-haiku-20241022",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": translation_prompt}],
                    temperature=0.3,
                )
                return {"text": response.content[0].text.strip()}

            elif provider == "ollama":
                import httpx
                ollama_url = config.get("ollama_url", "http://localhost:11434")
                url = f"{ollama_url.rstrip('/')}/api/chat"
                payload = {
                    "model": model or "llama3.2",
                    "messages": [{"role": "user", "content": translation_prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3},
                }
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    resp = await http_client.post(url, json=payload)
                    resp.raise_for_status()
                    return {"text": resp.json()["message"]["content"].strip()}

            else:
                log.warning("Translate: unknown provider %s", provider)
                return {"text": f"<translated:{lang}> {text}"}

        except Exception as exc:
            log.warning("Translate: provider %s failed (%s), returning placeholder", provider, exc)
            return {"text": f"<translated:{lang}> {text}"}


@register_node
class ConditionExecutor(BaseNodeExecutor):
    """Branch execution based on text content."""

    node_type = "condition"
    display_name = "Condition"
    category = "Logic"
    description = "Route data based on a condition (contains, regex, length, language)."
    default_config: dict[str, Any] = {
        "condition_type": "contains",
        "value": "",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [
            Port(name="true_branch", port_type="text", direction="output"),
            Port(name="false_branch", port_type="text", direction="output"),
        ]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        text = str(inputs.get("text", ""))
        ctype = config.get("condition_type", "contains")
        value = config.get("value", "")
        result = False

        if ctype == "contains":
            result = value.lower() in text.lower()
        elif ctype == "regex":
            result = bool(re.search(value, text))
        elif ctype == "length":
            try:
                result = len(text) > int(value)
            except (ValueError, TypeError):
                result = False
        elif ctype == "language":
            # Very naive language check
            result = value.lower() in text.lower()

        if result:
            return {"true_branch": text, "false_branch": None}
        else:
            return {"true_branch": None, "false_branch": text}


@register_node
class TextInjectExecutor(BaseNodeExecutor):
    """Paste text into the active application."""

    node_type = "text_inject"
    display_name = "Text Inject"
    category = "Output"
    description = "Inject text into the currently focused application."
    default_config: dict[str, Any] = {
        "method": "clipboard",  # "clipboard" or "keyboard"
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return []

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        text = inputs.get("text", "")
        method = config.get("method", "clipboard")
        if text:
            log.info("TextInject: injecting %d chars via %s", len(str(text)), method)

        try:
            from core.text_injector import TextInjector

            injector = TextInjector()
            use_clipboard = method == "clipboard"
            injector.inject(text, use_clipboard=use_clipboard)
        except Exception as exc:
            log.warning("TextInject: injection failed (%s)", exc)

        return {}


@register_node
class MergeExecutor(BaseNodeExecutor):
    """Combine multiple text inputs."""

    node_type = "merge"
    display_name = "Merge"
    category = "Processing"
    description = "Combine two text inputs with a separator."
    default_config: dict[str, Any] = {
        "separator": "\n\n",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [
            Port(name="text1", port_type="text", direction="input"),
            Port(name="text2", port_type="text", direction="input"),
        ]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        parts = [str(v) for v in inputs.values() if v is not None]
        sep = config.get("separator", "\n\n")
        return {"text": sep.join(parts)}


@register_node
class TemplateExecutor(BaseNodeExecutor):
    """Apply a text template with placeholders."""

    node_type = "template"
    display_name = "Template"
    category = "Processing"
    description = "Apply a template string with {input} placeholders."
    default_config: dict[str, Any] = {
        "template": "{input}",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="input", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        template = config.get("template", "{input}")
        try:
            result = template.format(**{k: str(v) for k, v in inputs.items()})
        except KeyError:
            result = template
        return {"text": result}


@register_node
class CustomExecutor(BaseNodeExecutor):
    """User-defined Python code node."""

    node_type = "custom"
    display_name = "Custom Code"
    category = "Utility"
    description = "Execute user-defined Python code."
    default_config: dict[str, Any] = {
        "code": "# inputs dict is available\n# return a dict of outputs\noutput = inputs.get('input', '')\nresult = {'output': output}",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="input", port_type="any", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="output", port_type="any", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        code = config.get("code", "")
        local_ns: dict[str, Any] = {"inputs": inputs, "result": {}}
        try:
            exec(code, {"__builtins__": {}}, local_ns)  # noqa: S102
        except Exception as exc:
            log.error("Custom node execution failed: %s", exc)
            return {"output": f"ERROR: {exc}"}
        return local_ns.get("result", {})


@register_node
class SaveToVaultExecutor(BaseNodeExecutor):
    """Save text to the knowledge vault."""

    node_type = "save_to_vault"
    display_name = "Save to Vault"
    category = "Output"
    description = "Persist text into trevo's knowledge vault."
    default_config: dict[str, Any] = {
        "title": "Untitled",
        "tags": "",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return []

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        text = inputs.get("text", "")
        title = config.get("title", "Untitled")
        log.info("SaveToVault: title=%s len=%d", title, len(str(text)))
        return {}


@register_node
class WebSearchExecutor(BaseNodeExecutor):
    """Search the web."""

    node_type = "web_search"
    display_name = "Web Search"
    category = "Utility"
    description = "Search the web for a query."
    default_config: dict[str, Any] = {
        "engine": "google",
        "num_results": 5,
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="query", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="results", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        query = inputs.get("query", "")
        log.info("WebSearch: query=%s", query[:80])
        return {"results": f"<search_results for: {query[:60]}>"}


@register_node
class FileReadExecutor(BaseNodeExecutor):
    """Read a file from disk."""

    node_type = "file_read"
    display_name = "File Read"
    category = "Input"
    description = "Read text content from a file."
    default_config: dict[str, Any] = {
        "path": "",
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return []

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        fpath = config.get("path", "")
        if not fpath:
            return {"text": ""}
        try:
            text = Path(fpath).read_text(encoding="utf-8")
        except Exception as exc:
            log.error("FileRead failed: %s", exc)
            text = f"ERROR: {exc}"
        return {"text": text}


@register_node
class FileWriteExecutor(BaseNodeExecutor):
    """Write text to a file."""

    node_type = "file_write"
    display_name = "File Write"
    category = "Output"
    description = "Write text content to a file."
    default_config: dict[str, Any] = {
        "path": "",
        "append": False,
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="text", port_type="text", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return []

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        fpath = config.get("path", "")
        text = str(inputs.get("text", ""))
        if not fpath:
            log.warning("FileWrite: no path configured")
            return {}
        try:
            p = Path(fpath)
            if config.get("append", False):
                with p.open("a", encoding="utf-8") as f:
                    f.write(text)
            else:
                p.write_text(text, encoding="utf-8")
            log.info("FileWrite: wrote %d chars to %s", len(text), fpath)
        except Exception as exc:
            log.error("FileWrite failed: %s", exc)
        return {}


@register_node
class DelayExecutor(BaseNodeExecutor):
    """Wait for a configurable number of seconds."""

    node_type = "delay"
    display_name = "Delay"
    category = "Utility"
    description = "Pause execution for a number of seconds."
    default_config: dict[str, Any] = {
        "seconds": 1.0,
    }

    @staticmethod
    def default_inputs() -> list[Port]:
        return [Port(name="input", port_type="any", direction="input")]

    @staticmethod
    def default_outputs() -> list[Port]:
        return [Port(name="output", port_type="any", direction="output")]

    async def execute(
        self, inputs: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        seconds = float(config.get("seconds", 1.0))
        await asyncio.sleep(seconds)
        # Pass through the first input value.
        value = next(iter(inputs.values()), None) if inputs else None
        return {"output": value}


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    """Execute, save, and load node-based workflows."""

    def __init__(self) -> None:
        self._running: bool = False
        self._node_results: dict[str, dict[str, Any]] = {}

    # ---- execution --------------------------------------------------------

    async def execute(
        self,
        workflow: Workflow,
        initial_data: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Execute the workflow and return per-node output dicts.

        Args:
            workflow: The workflow graph to execute.
            initial_data: Optional mapping of ``node_id -> {port: value}``
                used to seed specific nodes (e.g. injecting text for testing).
            progress_callback: Optional ``callable(node_id, status)`` invoked
                as each node starts / finishes.

        Returns:
            Mapping of ``node_id`` to the dict of output port values
            produced by that node.
        """
        self._running = True
        self._node_results = {}
        initial_data = initial_data or {}

        order = self._topological_sort(workflow)
        total = len(order)

        for idx, node_id in enumerate(order):
            if not self._running:
                log.warning("Workflow execution cancelled.")
                break

            node = workflow.nodes[node_id]
            if progress_callback:
                try:
                    progress_callback(node_id, "running", idx, total)
                except Exception:
                    pass

            # Gather inputs from connected upstream nodes.
            inputs = self._gather_inputs(workflow, node, initial_data)

            # Execute
            try:
                executor = get_executor(node.node_type)
                outputs = await executor.execute(inputs, node.config)
            except Exception as exc:
                log.error("Node %s (%s) failed: %s", node.id, node.label, exc)
                outputs = {"_error": str(exc)}

            self._node_results[node_id] = outputs

            if progress_callback:
                try:
                    progress_callback(node_id, "done", idx + 1, total)
                except Exception:
                    pass

        self._running = False
        return dict(self._node_results)

    def cancel(self) -> None:
        """Cancel a running workflow."""
        self._running = False

    # ---- internal helpers -------------------------------------------------

    def _gather_inputs(
        self,
        workflow: Workflow,
        node: WorkflowNode,
        initial_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect the input values for a node from upstream results."""
        inputs: dict[str, Any] = {}

        # Allow initial_data to seed a node.
        if node.id in initial_data:
            inputs.update(initial_data[node.id])

        for conn in workflow.connections:
            if conn.to_node != node.id:
                continue
            upstream = self._node_results.get(conn.from_node, {})
            value = upstream.get(conn.from_port)
            if value is not None:
                inputs[conn.to_port] = value

        return inputs

    @staticmethod
    def _topological_sort(workflow: Workflow) -> list[str]:
        """Return node ids in execution order (Kahn's algorithm)."""
        in_degree: dict[str, int] = {nid: 0 for nid in workflow.nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in workflow.nodes}

        for conn in workflow.connections:
            if conn.from_node in adjacency and conn.to_node in in_degree:
                adjacency[conn.from_node].append(conn.to_node)
                in_degree[conn.to_node] += 1

        queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            # Sort for deterministic ordering.
            queue.sort()
            nid = queue.pop(0)
            order.append(nid)
            for neighbour in adjacency[nid]:
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(order) != len(workflow.nodes):
            missing = set(workflow.nodes) - set(order)
            raise ValueError(
                f"Workflow contains a cycle involving nodes: {missing}"
            )
        return order

    # ---- serialisation ----------------------------------------------------

    def save_workflow(self, workflow: Workflow, path: Path) -> None:
        """Serialise *workflow* to a JSON file at *path*."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _workflow_to_dict(workflow)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        log.info("Saved workflow %r to %s", workflow.name, path)

    def load_workflow(self, path: Path) -> Workflow:
        """Deserialise a workflow from a JSON file."""
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _workflow_from_dict(raw)

    # ---- presets ----------------------------------------------------------

    @staticmethod
    def get_builtin_workflows() -> list[Workflow]:
        """Return a list of preset / example workflows."""
        return [
            _make_simple_dictation(),
            _make_formal_email(),
            _make_translate_inject(),
            _make_smart_assistant(),
        ]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _port_to_dict(port: Port) -> dict[str, Any]:
    return {
        "name": port.name,
        "port_type": port.port_type,
        "direction": port.direction,
        "connected_to": port.connected_to,
    }


def _port_from_dict(d: dict[str, Any]) -> Port:
    return Port(
        name=d["name"],
        port_type=d["port_type"],
        direction=d["direction"],
        connected_to=[tuple(pair) for pair in d.get("connected_to", [])],
    )


def _node_to_dict(node: WorkflowNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "label": node.label,
        "config": node.config,
        "inputs": [_port_to_dict(p) for p in node.inputs],
        "outputs": [_port_to_dict(p) for p in node.outputs],
        "position": list(node.position),
    }


def _node_from_dict(d: dict[str, Any]) -> WorkflowNode:
    return WorkflowNode(
        id=d["id"],
        node_type=d["node_type"],
        label=d["label"],
        config=d.get("config", {}),
        inputs=[_port_from_dict(p) for p in d.get("inputs", [])],
        outputs=[_port_from_dict(p) for p in d.get("outputs", [])],
        position=tuple(d.get("position", [0.0, 0.0])),
    )


def _conn_to_dict(c: WorkflowConnection) -> dict[str, Any]:
    return {
        "id": c.id,
        "from_node": c.from_node,
        "from_port": c.from_port,
        "to_node": c.to_node,
        "to_port": c.to_port,
    }


def _conn_from_dict(d: dict[str, Any]) -> WorkflowConnection:
    return WorkflowConnection(**d)


def _workflow_to_dict(w: Workflow) -> dict[str, Any]:
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description,
        "nodes": {nid: _node_to_dict(n) for nid, n in w.nodes.items()},
        "connections": [_conn_to_dict(c) for c in w.connections],
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat(),
    }


def _workflow_from_dict(d: dict[str, Any]) -> Workflow:
    nodes = {nid: _node_from_dict(nd) for nid, nd in d.get("nodes", {}).items()}
    connections = [_conn_from_dict(cd) for cd in d.get("connections", [])]
    return Workflow(
        id=d["id"],
        name=d["name"],
        description=d.get("description", ""),
        nodes=nodes,
        connections=connections,
        created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.now(timezone.utc),
        updated_at=datetime.fromisoformat(d["updated_at"]) if "updated_at" in d else datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Node factory helper
# ---------------------------------------------------------------------------

def create_node(
    node_type: str,
    label: str | None = None,
    config: dict[str, Any] | None = None,
    position: tuple[float, float] = (0.0, 0.0),
) -> WorkflowNode:
    """Create a new WorkflowNode with default ports from the executor registry.

    Args:
        node_type: Registered node type string.
        label: Display label. Defaults to the executor's display_name.
        config: Override config. Merged on top of the executor's defaults.
        position: Canvas position ``(x, y)``.

    Returns:
        A fully initialised :class:`WorkflowNode`.
    """
    cls = _NODE_EXECUTORS.get(node_type)
    if cls is None:
        raise KeyError(f"Unknown node type {node_type!r}")
    merged_config = dict(cls.default_config)
    if config:
        merged_config.update(config)
    return WorkflowNode(
        id=_uid(),
        node_type=node_type,
        label=label or cls.display_name,
        config=merged_config,
        inputs=cls.default_inputs(),
        outputs=cls.default_outputs(),
        position=position,
    )


# ---------------------------------------------------------------------------
# Preset workflows
# ---------------------------------------------------------------------------

def _chain_workflow(
    name: str,
    description: str,
    node_specs: list[tuple[str, dict[str, Any] | None]],
) -> Workflow:
    """Build a simple left-to-right chain workflow from a list of
    ``(node_type, config_override)`` tuples."""
    wf = Workflow(
        id=_uid(),
        name=name,
        description=description,
        nodes={},
        connections=[],
    )
    prev_node: WorkflowNode | None = None
    for i, (ntype, cfg) in enumerate(node_specs):
        node = create_node(ntype, config=cfg, position=(i * 220.0, 0.0))
        wf.add_node(node)
        if prev_node and prev_node.outputs and node.inputs:
            wf.connect(
                prev_node.id, prev_node.outputs[0].name,
                node.id, node.inputs[0].name,
            )
        prev_node = node
    return wf


def _make_simple_dictation() -> Workflow:
    return _chain_workflow(
        "Simple Dictation",
        "AudioInput -> STT -> TextPolish -> TextInject",
        [
            ("audio_input", None),
            ("stt", None),
            ("text_polish", {"style": "clean"}),
            ("text_inject", None),
        ],
    )


def _make_formal_email() -> Workflow:
    return _chain_workflow(
        "Formal Email",
        "AudioInput -> STT -> LLM (formal email) -> TextInject",
        [
            ("audio_input", None),
            ("stt", None),
            ("llm", {
                "system_prompt": (
                    "Rewrite the following text as a polished, formal email. "
                    "Keep the intent and key information. Be concise."
                ),
                "temperature": 0.4,
            }),
            ("text_inject", None),
        ],
    )


def _make_translate_inject() -> Workflow:
    return _chain_workflow(
        "Translate & Inject",
        "AudioInput -> STT -> Translate -> TextInject",
        [
            ("audio_input", None),
            ("stt", None),
            ("translate", {"target_language": "es"}),
            ("text_inject", None),
        ],
    )


def _make_smart_assistant() -> Workflow:
    """AudioInput -> STT -> Condition -> [LLM | TextPolish] -> TextInject."""
    wf = Workflow(
        id=_uid(),
        name="Smart Assistant",
        description="Route instructions to LLM, plain text to TextPolish",
        nodes={},
        connections=[],
    )

    audio = create_node("audio_input", position=(0, 100))
    stt = create_node("stt", position=(220, 100))
    cond = create_node("condition", config={
        "condition_type": "contains",
        "value": "?",
    }, position=(440, 100))
    llm = create_node("llm", config={
        "system_prompt": "Answer the user's question helpfully and concisely.",
    }, position=(660, 0))
    polish = create_node("text_polish", position=(660, 200))
    inject = create_node("text_inject", position=(880, 100))

    for n in [audio, stt, cond, llm, polish, inject]:
        wf.add_node(n)

    wf.connect(audio.id, "audio", stt.id, "audio")
    wf.connect(stt.id, "text", cond.id, "text")
    wf.connect(cond.id, "true_branch", llm.id, "text")
    wf.connect(cond.id, "false_branch", polish.id, "text")
    wf.connect(llm.id, "text", inject.id, "text")
    wf.connect(polish.id, "text", inject.id, "text")

    return wf
