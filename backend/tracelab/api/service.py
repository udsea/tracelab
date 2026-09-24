import asyncio
from pathlib import Path

from tracelab.api.jobs import Jobs
from tracelab.classifiers.presets import presets
from tracelab.classifiers.runner import ClassifierRunner
from tracelab.forks.runner import ForkRunner
from tracelab.ingestion.service import ensure_loaded
from tracelab.inspect_adapter.backend import InspectBackend
from tracelab.models.domain import (
    ProviderSettings,
)
from tracelab.providers.base import HTTPProvider, default_providers
from tracelab.sources.manager import Sources
from tracelab.storage.database import Database


class Service:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db = Database(data_dir / "tracelab.duckdb")
        self.jobs = Jobs(self.db)
        self.adapter = InspectBackend()
        self.sources = Sources(data_dir / "cache")
        self.load_locks = {}
        self.native_processes = []
        for item in default_providers():
            if not self.db.maybe("providers", item.id):
                self.db.put("providers", item)
        for item in presets():
            if not self.db.maybe("classifier_definitions", item.id):
                self.db.put("classifier_definitions", item)
        self.classifiers = ClassifierRunner(
            self.db, self.jobs, self.load_events, self.provider_factory
        )
        self.forks = ForkRunner(self.db, self.jobs, self.adapter, self.load_events, data_dir)

    def provider_factory(self, id):
        settings = ProviderSettings.model_validate(self.db.get("providers", id))
        return (HTTPProvider(settings), settings)

    async def load_events(self, id):
        trajectory = await ensure_loaded(self, id)
        if trajectory.metadata.get("indexState") not in (None, "READY"):
            raise ValueError(
                "Trajectory indexing is incomplete. Available events can be explored; finish or retry indexing before running analysis."
            )
        return await asyncio.to_thread(
            self.db.list, "events", "trajectory_id = ?", [id], 2000000, 0, "event_index"
        )

    async def dispatch(self, method: str, p: dict):
        from tracelab.api import (
            routes_analysis,
            routes_execution,
            routes_research,
            routes_sources,
            routes_trajectory,
            routes_workspace,
        )

        handlers = {
            "health": routes_workspace.handle,
            "workspaces.list": routes_workspace.handle,
            "workspaces.create": routes_workspace.handle,
            "workspaces.open": routes_workspace.handle,
            "workspaces.demo": routes_workspace.handle,
            "experiments.list": routes_workspace.handle,
            "import": routes_workspace.handle,
            "trajectories.list": routes_trajectory.handle,
            "trajectories.get": routes_trajectory.handle,
            "trajectories.summary": routes_trajectory.handle,
            "events.list": routes_trajectory.handle,
            "events.get": routes_trajectory.handle,
            "events.raw": routes_trajectory.handle,
            "timeline": routes_trajectory.handle,
            "annotations.save": routes_analysis.handle,
            "annotations.delete": routes_analysis.handle,
            "segments.save": routes_analysis.handle,
            "segments.delete": routes_analysis.handle,
            "segments.run": routes_analysis.handle,
            "classifiers.list": routes_analysis.handle,
            "classifiers.save": routes_analysis.handle,
            "classifiers.run": routes_analysis.handle,
            "results.get": routes_analysis.handle,
            "forks.list": routes_execution.handle,
            "forks.run": routes_execution.handle,
            "compare.pair": routes_execution.handle,
            "compare.groups": routes_execution.handle,
            "compare.members": routes_execution.handle,
            "search": routes_trajectory.handle,
            "search.index": routes_trajectory.handle,
            "jobs.list": routes_execution.handle,
            "jobs.get": routes_execution.handle,
            "jobs.cancel": routes_execution.handle,
            "providers.list": routes_execution.handle,
            "providers.save": routes_execution.handle,
            "inspect.open": routes_execution.handle,
        }
        handler = handlers.get(method)
        if method in routes_sources.METHODS:
            handler = routes_sources.handle
        if method in routes_research.METHODS:
            handler = routes_research.handle
        if handler is None:
            raise ValueError(f"Unknown method: {method}")
        return await handler(self, method, p)

    async def close(self):
        await self.jobs.close()
        for process in self.native_processes:
            if process.returncode is None:
                process.terminate()
                await process.wait()
        self.db.close()
        self.sources.close()
