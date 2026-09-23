import json
import re

from huggingface_hub import HfApi, HfFileSystem

from tracelab.sources.base import SourceEntry, SourceMetadata
from tracelab.sources.cache import key, source_key
from tracelab.sources.refs import child_ref
from tracelab.sources.remote import BLOCK_SIZE, CachedRemoteProvider


class HuggingFaceSourceProvider(CachedRemoteProvider):
    def __init__(self, cache, api=None, filesystem=None):
        super().__init__(cache)
        # Standard Hub authentication: HF_TOKEN or the user's existing hf auth login.
        self.api = api or HfApi()
        self.fs = filesystem or HfFileSystem()

    def resolve(self, ref, fresh=False):
        if ref.metadata.get("commitSha"):
            return ref
        meta = ref.metadata
        id = key(["hf-revision", meta["repoType"], meta["repoId"], ref.revision])
        cached = self.cache.get("metadata", id)
        offline = False
        if cached and not fresh:
            commit = json.loads(cached)["commitSha"]
        else:
            try:
                commit = self.api.repo_info(
                    meta["repoId"], repo_type=meta["repoType"], revision=ref.revision
                ).sha
            except Exception:
                if not cached:
                    raise OSError(
                        "Cannot access this Hugging Face repository. Check its name, network, and standard hf auth login."
                    ) from None
                commit = json.loads(cached)["commitSha"]
                offline = True
            self.cache.put("metadata", id, json.dumps({"commitSha": commit}).encode())
        if not re.fullmatch(r"[a-fA-F0-9]{40}", commit):
            raise ValueError("Hub did not return a concrete commit SHA")
        result = ref.model_copy(deep=True)
        result.revision = commit
        result.metadata.update(
            commitSha=commit,
            requestedRevision=meta.get("requestedRevision", ref.revision),
            offlineMetadata=offline,
        )
        return child_ref(result, meta.get("path", ""))

    def stat(self, ref):
        ref = self.resolve(ref)
        meta = ref.metadata
        if not meta.get("path"):
            return SourceMetadata(ref=ref, name=meta["repoId"], is_directory=True)
        if ref.size_bytes is not None:
            return SourceMetadata(
                ref=ref, name=meta["path"].rsplit("/", 1)[-1], size_bytes=ref.size_bytes
            )
        id = key(["hf-stat", ref.uri])
        cached = self.cache.get("metadata", id)
        if cached:
            return SourceMetadata.model_validate_json(cached)
        items = self.api.get_paths_info(
            meta["repoId"], [meta["path"]], repo_type=meta["repoType"], revision=ref.revision
        )
        if not items:
            raise FileNotFoundError(meta["path"])
        entry = self.entry(ref, items[0])
        value = SourceMetadata(
            **{
                k: v
                for k, v in entry.wire().items()
                if k in {"ref", "name", "isDirectory", "sizeBytes", "modified"}
            }
        )
        self.cache.put(
            "metadata", id, value.model_dump_json(by_alias=True).encode(), source_key(value.ref)
        )
        return value

    def entry(self, ref, item):
        path = item.path
        child = child_ref(ref, path)
        size = getattr(item, "size", None)
        child.size_bytes = size
        child.etag = getattr(item, "blob_id", None)
        lfs = getattr(item, "lfs", None)
        child.checksum = getattr(lfs, "sha256", None) if lfs else None
        return SourceEntry(
            ref=child,
            name=path.rsplit("/", 1)[-1],
            path=path,
            is_directory=size is None,
            size_bytes=size,
            cached_bytes=self.cache.stats(source_key(child))["usageBytes"],
        )

    def list(self, ref):
        ref = self.resolve(ref)
        id = key(["hf-tree", ref.uri])
        cached = self.cache.get("metadata", id)
        if cached:
            entries = [SourceEntry.model_validate(x) for x in json.loads(cached)]
            for entry in entries:
                entry.cached_bytes = self.cache.stats(source_key(entry.ref))["usageBytes"]
            return entries
        meta = ref.metadata
        entries = [
            self.entry(ref, item)
            for item in self.api.list_repo_tree(
                meta["repoId"],
                path_in_repo=meta.get("path") or None,
                repo_type=meta["repoType"],
                revision=ref.revision,
                recursive=False,
                expand=False,
            )
        ]
        self.cache.put(
            "metadata", id, json.dumps([e.wire() for e in entries]).encode(), source_key(ref)
        )
        return entries

    def fetch_range(self, ref, start, end):
        # fsspec's no-cache mode avoids hidden read-ahead. TraceLab persists exact fixed ranges.
        with self.fs.open(
            ref.uri.removeprefix("hf://"), "rb", block_size=BLOCK_SIZE, cache_type="none"
        ) as stream:
            stream.seek(start)
            return stream.read(end - start)

    def glob(self, ref, pattern):
        import fnmatch

        ref = self.resolve(ref)
        id = key(["hf-tree-recursive", ref.uri])
        cached = self.cache.get("metadata", id)
        if cached:
            entries = [SourceEntry.model_validate(x) for x in json.loads(cached)]
        else:
            meta = ref.metadata
            entries = [
                self.entry(ref, item)
                for item in self.api.list_repo_tree(
                    meta["repoId"],
                    path_in_repo=meta.get("path") or None,
                    repo_type=meta["repoType"],
                    revision=ref.revision,
                    recursive=True,
                    expand=False,
                )
                if getattr(item, "size", None) is not None
            ]
            self.cache.put(
                "metadata", id, json.dumps([e.wire() for e in entries]).encode(), source_key(ref)
            )
        return [e for e in entries if fnmatch.fnmatch(e.path, pattern)]
