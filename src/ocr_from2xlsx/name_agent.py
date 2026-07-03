"""Optional, config-driven handwritten-name suggestion agent.

When unconfigured/disabled/unknown-provider, `build_agent` returns a NullNameAgent whose `suggest`
returns None, so the pipeline is unaffected. The cloud ClaudeNameAgent's network call is exercised only
by a manual spike, never by CI.
"""
from __future__ import annotations

import base64
import json
import os
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

DEFAULT_NAME_AGENT_PROMPT = "讀出圖片中的手寫中文姓名，只回傳姓名本身，不要其他文字。"
DEFAULT_NAME_AGENT_MODEL = "claude-fable-5"


class NameAgent(Protocol):
    def suggest(self, crop_path: str) -> str | None:
        ...


class NullNameAgent:
    def suggest(self, crop_path: str) -> str | None:
        return None


@dataclass(slots=True)
class NameAgentConfig:
    enabled: bool = False
    provider: str = ""
    model: str = DEFAULT_NAME_AGENT_MODEL
    endpoint: str = ""
    prompt: str = DEFAULT_NAME_AGENT_PROMPT
    api_key_env: str = "ANTHROPIC_API_KEY"


def _require_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a bool")


def _require_string(value: Any, field_name: str) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"{field_name} must be a string")


def load_config(path: Path | str) -> NameAgentConfig:
    path = Path(path)
    if not path.is_file():
        return NameAgentConfig(enabled=False)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    enabled = data.get("enabled", False)
    provider = data.get("provider", "")
    model = data.get("model", DEFAULT_NAME_AGENT_MODEL)
    endpoint = data.get("endpoint", "")
    prompt = data.get("prompt", DEFAULT_NAME_AGENT_PROMPT)
    api_key_env = data.get("api_key_env", "ANTHROPIC_API_KEY")
    return NameAgentConfig(
        enabled=_require_bool(enabled, "enabled"),
        provider=_require_string(provider, "provider"),
        model=_require_string(model, "model"),
        endpoint=_require_string(endpoint, "endpoint"),
        prompt=_require_string(prompt, "prompt"),
        api_key_env=_require_string(api_key_env, "api_key_env"),
    )


class ClaudeNameAgent:
    """Calls an Anthropic-style messages endpoint with the name crop. Network = spike-only."""

    def __init__(self, config: NameAgentConfig) -> None:
        self.config = config

    def suggest(self, crop_path: str) -> str | None:
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key or not self.config.endpoint:
            return None
        try:
            image_b64 = base64.b64encode(Path(crop_path).read_bytes()).decode("ascii")
            payload = {
                "model": self.config.model,
                "max_tokens": 32,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": self.config.prompt},
                        ],
                    }
                ],
            }
            request = urllib.request.Request(
                self.config.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            parts = body.get("content") or []
            for part in parts:
                if part.get("type") == "text":
                    return (part.get("text") or "").strip() or None
            return None
        except Exception:
            # Any failure (network, auth, parse) degrades to "no suggestion" — pipeline unaffected.
            return None


def build_agent(config: NameAgentConfig) -> NameAgent:
    if not config.enabled:
        return NullNameAgent()
    if not config.model or not config.endpoint:
        return NullNameAgent()
    if not os.environ.get(config.api_key_env):
        return NullNameAgent()
    if config.provider == "claude":
        return ClaudeNameAgent(config)
    return NullNameAgent()
