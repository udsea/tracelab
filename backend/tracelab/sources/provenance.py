"""Resolve the files owned by a selected normalized run without fetching contents."""

from tracelab.models.domain import SourceRef
from tracelab.sources.cache import source_key


def related_refs(trajectory, ref):
    bundle = trajectory["metadata"].get("runReference", {}).get("locator", {}).get("bundle")
    values = [ref]
    if bundle:
        values += [
            SourceRef.model_validate(entry["ref"])
            for category in ("streams", "scores", "configs")
            for entry in bundle[category]
        ]
    values += [SourceRef.model_validate(v) for v in trajectory["metadata"].get("offlineFiles", [])]
    return list({source_key(value): value for value in values}.values())


def cache_stats(cache, refs):
    result = cache.stats(source_key(refs[0]))
    for ref in refs[1:]:
        value = cache.stats(source_key(ref))
        for field in ("usageBytes", "pinnedBytes"):
            result[field] += value[field]
        for category, size in value["categories"].items():
            result["categories"][category] = result["categories"].get(category, 0) + size
    return result
