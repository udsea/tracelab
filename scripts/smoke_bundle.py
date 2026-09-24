"""Exercise the packaged runtime and a populated-database restart without any model calls."""

import itertools
import json
import plistlib
import select
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def sidecar(binary: Path, data: str):
    with tempfile.TemporaryFile(mode="w+t") as logs:
        process = subprocess.Popen(
            [str(binary), "--stdio", "--data-dir", data],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=logs,
            text=True,
        )
        ids = itertools.count(1)

        def rpc(method, params=None):
            request_id = next(ids)
            process.stdin.write(
                json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n"
            )
            process.stdin.flush()
            if not select.select([process.stdout], [], [], 90)[0]:
                raise TimeoutError(method)
            line = process.stdout.readline()
            if not line:
                logs.seek(0)
                raise RuntimeError(logs.read())
            reply = json.loads(line)
            assert reply["id"] == request_id and "error" not in reply, reply
            return reply["result"]

        try:
            yield rpc
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
            if process.returncode:
                logs.seek(0)
                raise RuntimeError(logs.read())


def main():
    binary = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "src-tauri/target/release/bundle/macos/TraceLab.app/Contents/Resources/backend/tracelab-backend"
    ).resolve()
    app_contents = binary.parents[2]
    if (app_contents / "Info.plist").is_file():
        with open(app_contents / "Info.plist", "rb") as stream:
            info = plistlib.load(stream)
        icon = info["CFBundleIconFile"]
        assert (app_contents / "Resources" / icon).is_file()
    with tempfile.TemporaryDirectory(prefix="tracelab-bundle-smoke-") as data:
        with sidecar(binary, data) as rpc:
            health = rpc("health")
            workspace = rpc("workspaces.demo")
            page = rpc("trajectories.list", {"workspaceId": workspace["id"]})
            assert page["total"] == 6
            tid = page["items"][0]["id"]
            trajectory = rpc("trajectories.get", {"id": tid})
            assert trajectory["capabilities"]["checkpointRestored"] is False
            events = rpc("events.list", {"trajectoryId": tid, "offset": 180, "limit": 10})
            assert events["total"] == 487 and len(events["items"]) == 10
            assert events["items"][0]["index"] == 180
            timeline = rpc("timeline", {"trajectoryId": tid})
            assert len(timeline["results"]) == 98 and len(timeline["segments"]) == 5
            result = rpc("results.get", {"id": timeline["results"][0]["id"]})
            evidence = rpc("events.get", {"id": result["output"]["evidenceEventIds"][0]})
            assert evidence["event"]["trajectoryId"] == tid
            groups = rpc(
                "compare.groups",
                {
                    "workspaceId": workspace["id"],
                    "groups": [
                        {"filters": [{"field": "condition", "value": condition}]}
                        for condition in ["baseline", "task briefing"]
                    ],
                },
            )
            assert [g["trajectories"] for g in groups] == [4, 2]
            overview = rpc("analysis.overview", {"trajectoryId": tid})
            assert len(overview["coordinates"]["points"]) == 487
            assert overview["outline"]
            definition = rpc(
                "analysis.save",
                {
                    "name": "Packaged rule smoke",
                    "detectorType": "rule",
                    "parameters": {"contains": ["evaluator", "tests"]},
                },
            )
            analysis_job = rpc(
                "analysis.run", {"definitionId": definition["id"], "trajectoryIds": [tid]}
            )
            deadline = time.monotonic() + 30
            while True:
                analysis_job = rpc("jobs.get", {"id": analysis_job["id"]})
                assert analysis_job["status"] not in ("failed", "cancelled"), analysis_job
                if analysis_job["status"] == "complete":
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("Packaged rule detector")
                time.sleep(0.1)
            shared_signals = rpc("analysis.signals", {"trajectoryId": tid})
            rule_signal = next(s for s in shared_signals if s["sourceType"] == "rule")
            detail = rpc("analysis.signal", {"trajectoryId": tid, "id": rule_signal["id"]})
            assert detail["signal"]["provenance"]["implementationHash"]
            assert len(detail["signal"]["provenance"]["inputManifest"]["inputEventIds"]) == 487
            # The completed detector intentionally invalidates the derived overview.
            # Compare restart against that final state, not the pre-detector snapshot.
            overview = rpc("analysis.overview", {"trajectoryId": tid})
            source_workspace = rpc("workspaces.create", {"name": "Packaged format smoke"})
            fixture = Path(data) / "atif.json"
            fixture.write_text(
                json.dumps(
                    {
                        "schema_version": "ATIF-v1.8",
                        "trajectory_id": "packaged",
                        "steps": [
                            {
                                "step_id": 1,
                                "source": "agent",
                                "message": "Packaged streaming parser works",
                            }
                        ],
                    }
                )
            )
            ref = rpc("sources.connect", {"uri": str(fixture), "kind": "local"})["ref"]
            assert rpc("sources.detect", {"ref": ref})["detections"][0]["format"] == "atif"
            rpc("sources.add", {"workspaceId": source_workspace["id"], "refs": [ref]})
            deadline = time.monotonic() + 30
            while True:
                imported = rpc("trajectories.list", {"workspaceId": source_workspace["id"]})[
                    "items"
                ]
                if imported and imported[0]["loaded"]:
                    break
                jobs = rpc("jobs.list")
                assert not any(j["status"] == "failed" for j in jobs), jobs
                if time.monotonic() > deadline:
                    raise TimeoutError("Packaged ATIF indexing")
                time.sleep(0.1)
            source_tid = imported[0]["id"]
            assert (
                rpc("trajectories.get", {"id": source_tid})["capabilities"]["contextOnly"] is False
            )
            assert rpc("sources.info", {"trajectoryId": source_tid})["format"] == "atif"
        with sidecar(binary, data) as rpc:
            assert workspace["id"] in [w["id"] for w in rpc("workspaces.list")]
            assert rpc("analysis.overview", {"trajectoryId": tid}) == overview
            assert len(rpc("analysis.signals", {"trajectoryId": tid})) == len(shared_signals)
            assert rpc("trajectories.list", {"workspaceId": workspace["id"]})["total"] == 6
            assert rpc("events.get", {"id": evidence["event"]["id"]})["event"] == evidence["event"]
            assert rpc("trajectories.get", {"id": source_tid})["trajectory"]["loaded"]
        print(
            json.dumps(
                {
                    "status": "passed",
                    "inspectVersion": health["inspectVersion"],
                    "trajectories": 6,
                    "eventsPerTrajectory": 487,
                    "signals": 98,
                    "evidenceResolved": True,
                    "populatedRestart": True,
                    "modelCalls": 0,
                    "streamingAtifRestart": True,
                    "bundleIcon": icon if "icon" in locals() else "not an app bundle",
                }
            )
        )


if __name__ == "__main__":
    main()
