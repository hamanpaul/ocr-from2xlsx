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
from typing import Protocol


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
    model: str = ""
    endpoint: str = ""
    prompt: str = "讀出圖片中的手寫中文姓名，只回傳姓名本身，不要其他文字。"
    api_key_env: str = "ANTHROPIC_API_KEY"


def load_config(path: Path | str) -> NameAgentConfig:
    path = Path(path)
    if not path.is_file():
        return NameAgentConfig(enabled=False)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return NameAgentConfig(
        enabled=bool(data.get("enabled", False)),
        provider=str(data.get("provider", "")),
        model=str(data.get("model", "")),
        endpoint=str(data.get("endpoint", "")),
        prompt=str(data.get("prompt", NameAgentConfig.prompt)),
        api_key_env=str(data.get("api_key_env", "ANTHROPIC_API_KEY")),
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
    if config.provider == "claude":
        return ClaudeNameAgent(config)
    return NullNameAgent()
