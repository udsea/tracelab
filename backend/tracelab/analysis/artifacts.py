"""Explicit import of scalar measurements; tensors remain in external artifacts."""

import hashlib
import math
from pathlib import Path

import duckdb

from tracelab.analysis.models import AnalysisSignal, ArtifactRef, ModelInternalSource
from tracelab.models.domain import now


def import_parquet(db, trajectory_id, events, request):
    path = Path(request["uri"]).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".parquet":
        raise ValueError("Select a local Parquet scalar measurement file")
    event_column = request.get("eventColumn", "event_index")
    score_column = request.get("scoreColumn", "score")
    measurement = request.get("measurement", "probe")
    if measurement not in ("probe", "logit", "sae"):
        raise ValueError("Expected probe, logit or sae measurement")
    by_index = {e["index"]: e["id"] for e in events}
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
    artifact = ArtifactRef(
        trajectory_id=trajectory_id,
        uri=str(path),
        format="parquet",
        metadata={
            "measurement": measurement,
            "sha256": sha.hexdigest(),
            "sizeBytes": path.stat().st_size,
        },
    )
    source = ModelInternalSource(
        trajectory_id=trajectory_id,
        artifact_ids=[artifact.id],
        measurement=measurement,
        model=request.get("model"),
        metadata={"eventColumn": event_column, "scoreColumn": score_column},
    )
    con = duckdb.connect()
    try:
        relation = con.read_parquet(str(path))
        if event_column not in relation.columns or score_column not in relation.columns:
            raise ValueError("Selected event/score columns are absent")
        # Identifiers are validated against actual columns, then SQL-quoted.
        columns = ", ".join(
            '"' + name.replace('"', '""') + '"' for name in (event_column, score_column)
        )
        rows = relation.project(columns).limit(100001).fetchall()
        if len(rows) > 100000:
            raise ValueError("Select a scalar measurement export with at most 100,000 rows")
        output = []
        for index, score in rows:
            if (
                not isinstance(index, int)
                or index not in by_index
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
            ):
                raise ValueError("Each row needs a valid event index and finite numeric score")
            output.append(
                AnalysisSignal(
                    trajectory_id=trajectory_id,
                    name=request.get("name", measurement),
                    source_type=measurement,
                    channel="WHITE_BOX",
                    start_event_index=index,
                    end_event_index=index,
                    score=float(score),
                    evidence_event_ids=[by_index[index]],
                    artifact_ref=artifact.id,
                    provenance={
                        "internalSource": source.wire(),
                        "artifactChecksum": sha.hexdigest(),
                        "createdAt": now(),
                        "implementationVersion": "parquet-scalar-v1",
                        "inputEventIds": [by_index[index]],
                        "rawResult": {"index": index, "score": score},
                    },
                    metadata={"laneId": source.id},
                )
            )
        # Validate the entire selected export before persisting any records.
        db.put("artifacts", artifact)
        db.put("internal_sources", source)
        db.put_many("analysis_signals", output)
        return {"artifact": artifact.wire(), "source": source.wire(), "count": len(output)}
    finally:
        con.close()
