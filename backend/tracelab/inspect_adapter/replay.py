import asyncio
import os
from pathlib import Path
from typing import Annotated

from inspect_ai import Task, eval_async
from inspect_ai.dataset import Sample
from inspect_ai.log import transcript
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    GenerateConfig,
    get_model,
)
from inspect_ai.solver import generate, solver
from pydantic import Field, TypeAdapter

from tracelab.forks.context import GENERATION_PARAMETERS
from tracelab.inspect_adapter.tool_catalog import recorded_tool_info
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
    execution=None,
    tool_catalog=None,
) -> dict:
    settings = ProviderSettings.model_validate(provider)
    parsed = [MESSAGE.validate_python(m) for m in messages]
    # Public Inspect API; do not reuse original solvers, executable task code, or sandbox state.
    if set(parameters) - GENERATION_PARAMETERS:
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

    @solver
    def recorded_continuation():
        async def solve(state, generate):
            # ToolInfo contains schemas only. No Tool/ToolDef, execute_tools(),
            # original solver, sandbox, or source task is ever installed.
            tools = [
                recorded_tool_info(t.name, t.description, t.parameters_schema)
                for t in tool_catalog.tools
            ]
            while not execution.termination:
                await asyncio.sleep(0)  # Deliver cancellation before starting another model call.
                execution.start_step()
                output = await inspect_model.generate(
                    state.messages, tools=tools, tool_choice="auto", config=config, cache=False
                )
                state.output = output
                state.messages.append(output.message)
                raw = next(
                    (
                        e.model_dump(mode="json")
                        for e in reversed(transcript().events)
                        if getattr(e, "event", None) == "model"
                    ),
                    None,
                )
                try:
                    results = execution.on_output(output.model_dump(mode="json"), raw)
                except Exception:
                    execution.termination = "tool_resolution_error"
                    raise
                state.messages.extend(MESSAGE.validate_python(m) for m in results)
            state.completed = True
            return state

        return solve

    task = Task(
        name="tracelab_context_fork",
        dataset=[Sample(id=sample_id, input=parsed, metadata=metadata)],
        solver=recorded_continuation() if execution is not None else generate(tool_calls="none"),
        scorer=None,
        metadata=metadata,
    )
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    evaluation = asyncio.create_task(
        eval_async(
            task,
            model=inspect_model,
            log_dir=log_dir,
            log_format="eval",
            score=False,
            ctl_server=False,
            max_samples=1,
            retry_on_error=0,
        )
    )
    try:
        logs = await asyncio.shield(evaluation)
    except asyncio.CancelledError:
        # Inspect can swallow cancellation internally. Own the outer cancellation
        # and join cleanup before releasing the process-wide execution lock.
        evaluation.cancel()
        await asyncio.gather(evaluation, return_exceptions=True)
        raise
    # Inspect may consume cancellation and return an empty/cancelled log list.
    # Propagate it to TraceLab instead of recording an infrastructure failure.
    if (asyncio.current_task() and asyncio.current_task().cancelling()) or any(
        log.status == "cancelled" for log in logs
    ):
        raise asyncio.CancelledError
    if not logs:
        raise RuntimeError("Inspect returned no execution log")
    log = logs[0]
    if execution is not None:
        execution.trajectory.metadata["logPath"] = log.location
    if log.status != "success" or not log.samples or log.samples[0].error:
        error = log.samples[0].error if log.samples else log.error
        raise RuntimeError(
            f"Inspect continuation failed: {getattr(error, 'message', None) or log.status}; log: {log.location}"
        )
    return {"logPath": log.location, "sample": log.samples[0].model_dump(mode="json")}
