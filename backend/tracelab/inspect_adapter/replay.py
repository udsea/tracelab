import os
from pathlib import Path
from typing import Annotated

from inspect_ai import Task, eval_async
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    GenerateConfig,
    get_model,
)
from inspect_ai.solver import generate
from pydantic import Field, TypeAdapter

from tracelab.models.domain import ProviderSettings

MESSAGE = TypeAdapter(
    Annotated[
        ChatMessageSystem | ChatMessageUser | ChatMessageAssistant | ChatMessageTool,
        Field(discriminator="role"),
    ]
)


async def continue_context(
    *,
    messages: list[dict],
    model: str,
    provider: dict,
    parameters: dict,
    log_dir: str,
    sample_id: str,
    metadata: dict,
) -> dict:
    settings = ProviderSettings.model_validate(provider)
    parsed = [MESSAGE.validate_python(m) for m in messages]
    # Public Inspect API; do not reuse original solvers, executable task code, or sandbox state.
    allowed = {
        "temperature",
        "max_tokens",
        "top_p",
        "top_k",
        "seed",
        "reasoning_effort",
        "reasoning_tokens",
        "stop_seqs",
    }
    if set(parameters) - allowed:
        raise ValueError("Unsupported fork generation parameter")
    config = GenerateConfig(max_retries=0, timeout=180, **parameters)
    prefix = "anthropic" if settings.kind == "anthropic" else "openai"
    if settings.id == "openrouter" and model.startswith("openrouter/"):
        model = model.removeprefix("openrouter/")
    full_model = model if model.startswith(f"{prefix}/") else f"{prefix}/{model}"
    key = os.environ.get(settings.api_key_env, "")
    if not key and not settings.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError(f"Set {settings.api_key_env} in the backend environment")
    inspect_model = get_model(
        full_model, base_url=settings.base_url, api_key=key or "local", config=config, memoize=False
    )
    task = Task(
        name="tracelab_context_fork",
        dataset=[Sample(id=sample_id, input=parsed, metadata=metadata)],
        solver=generate(tool_calls="none"),
        scorer=None,
        metadata=metadata,
    )
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logs = await eval_async(
        task,
        model=inspect_model,
        log_dir=log_dir,
        log_format="eval",
        score=False,
        ctl_server=False,
        max_samples=1,
        retry_on_error=0,
    )
    log = logs[0]
    if log.status != "success" or not log.samples or log.samples[0].error:
        error = log.samples[0].error if log.samples else log.error
        raise RuntimeError(
            f"Inspect continuation failed: {getattr(error, 'message', None) or log.status}; log: {log.location}"
        )
    return {"logPath": log.location, "sample": log.samples[0].model_dump(mode="json")}
