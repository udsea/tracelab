import json
import os
from typing import Protocol
from urllib.parse import urlparse

import httpx

from tracelab.models.domain import ProviderSettings


class ModelProvider(Protocol):
    async def generate_structured(
        self, *, model: str, prompt: str, schema: dict, parameters: dict
    ) -> dict: ...


class HTTPProvider:
    """No SDK auto-retries. Output parsing/validation and its one retry belong to the runner."""

    def __init__(self, settings: ProviderSettings):
        self.settings = settings

    async def generate_structured(
        self, *, model: str, prompt: str, schema: dict, parameters: dict
    ) -> dict:
        cfg = self.settings
        key = os.environ.get(cfg.api_key_env, "")
        local = urlparse(cfg.base_url).hostname in ("localhost", "127.0.0.1", "::1")
        if not key and not local:
            raise ValueError(
                f"Set {cfg.api_key_env} in the backend environment before running {cfg.name}."
            )
        # Structural arguments are application-owned; generation knobs cannot replace them.
        allowed = {
            "temperature",
            "top_p",
            "max_tokens",
            "seed",
            "frequency_penalty",
            "presence_penalty",
        }
        extra = set(parameters) - allowed
        if extra:
            raise ValueError(f"Unsupported classifier parameters: {', '.join(sorted(extra))}")
        headers = {"Content-Type": "application/json"}
        if cfg.kind == "anthropic":
            headers |= {"x-api-key": key, "anthropic-version": "2023-06-01"}
            body = {
                "model": model,
                "max_tokens": 4096,
                **parameters,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "name": "record_analysis",
                        "description": "Record structured trajectory analysis",
                        "input_schema": schema,
                    }
                ],
                "tool_choice": {"type": "tool", "name": "record_analysis"},
            }
            url = cfg.base_url.rstrip("/") + "/messages"
        else:
            headers["Authorization"] = f"Bearer {key or 'local'}"
            body = {
                "model": model,
                **parameters,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "trajectory_analysis",
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
            url = cfg.base_url.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
            response = await client.post(url, headers=headers, json=body)
        if response.is_error:
            # Provider response bodies can echo private input. Keep them out of UI error summaries.
            raise RuntimeError(
                f"{cfg.name} returned HTTP {response.status_code}. Check endpoint, model, credentials and limits."
            )
        raw = response.json()
        if cfg.kind == "anthropic":
            matches = [
                b["input"]
                for b in raw.get("content", [])
                if b.get("type") == "tool_use" and b.get("name") == "record_analysis"
            ]
            output = matches[0] if len(matches) == 1 else None
        else:
            choices = raw.get("choices") or []
            output = choices[0].get("message", {}).get("content") if choices else None
        return {"output": output, "raw": raw, "request": body}


def decode_output(value):
    # Deliberately no markdown stripping, JSON repair, coercion, or fallback label.
    return json.loads(value) if isinstance(value, str) else value


def default_providers() -> list[ProviderSettings]:
    return [
        ProviderSettings(
            id="openai",
            name="OpenAI-compatible",
            kind="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            default_model="",
        ),
        ProviderSettings(
            id="openrouter",
            name="OpenRouter",
            kind="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            default_model="",
        ),
        ProviderSettings(
            id="anthropic",
            name="Anthropic",
            kind="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key_env="ANTHROPIC_API_KEY",
            default_model="",
        ),
        ProviderSettings(
            id="local",
            name="Local / vLLM",
            kind="openai_compatible",
            base_url="http://127.0.0.1:8000/v1",
            api_key_env="LOCAL_API_KEY",
            default_model="",
        ),
    ]
