import io
import json
import time
import uuid
from urllib.parse import urlparse

import httpx

from tracelab.sources.base import RangeReader, SourceEntry, SourceMetadata, recursive_glob
from tracelab.sources.cache import key, source_key
from tracelab.sources.refs import source_ref

BLOCK_SIZE = 64 * 1024


class CachedRemoteProvider:
    def __init__(self, cache):
        self.cache = cache

    def open(self, ref):
        ref = self.stat(ref).ref
        if ref.size_bytes is None:
            raise ValueError(
                "Source does not report a content length; use a local file or an HTTP manifest with sizes"
            )
        return io.BufferedReader(RangeReader(self, ref, ref.size_bytes), buffer_size=BLOCK_SIZE)

    def read_range(self, ref, start, end):
        if start < 0 or end < start:
            raise ValueError("Invalid byte range")
        ref = self.stat(ref).ref
        source = source_key(ref)
        complete = self.cache.get_path("files", source)
        if complete:
            with open(complete, "rb") as stream:
                stream.seek(start)
                return stream.read(end - start)
        size = ref.size_bytes
        if size is None:
            raise ValueError("Source size is unavailable")
        end = min(size, end)
        result = bytearray()
        for offset in range(start // BLOCK_SIZE * BLOCK_SIZE, end, BLOCK_SIZE):
            stop = min(size, offset + BLOCK_SIZE)
            id = key([source, offset, stop])
            block = self.cache.get("ranges", id)
            complete = self.cache.get_path("files", source)
            if block is None and complete:
                with open(complete, "rb") as stream:
                    stream.seek(offset)
                    block = stream.read(stop - offset)
            if block is None:
                try:
                    block = self.fetch_range(ref, offset, stop)
                except Exception as exc:
                    cached = self.cache.stats(source)["usageBytes"]
                    raise OSError(
                        f"Remote source unavailable. {cached:,} raw bytes cached; bytes {offset}–{stop} unavailable. Indexed events remain local. {type(exc).__name__}"
                    ) from exc
                self.cache.transferred_bytes += len(block)
                self.cache.requests += 1
                if len(block) != stop - offset:
                    raise OSError("Remote source returned a truncated byte range")
                self.cache.put("ranges", id, block, source)
            result.extend(block[max(0, start - offset) : min(len(block), end - offset)])
        return bytes(result)

    def supports_random_access(self, ref):
        return ref.size_bytes is not None

    def glob(self, ref, pattern):
        return recursive_glob(self, ref, pattern)

    def pin(self, ref, progress=None):
        ref = self.stat(ref).ref
        source = source_key(ref)
        # Stream to disk: pinning must not assemble a multi-GB file in memory.
        path = self.cache.path("files", source)
        path.parent.mkdir(exist_ok=True)
        temporary = path.with_suffix(".download")
        try:
            with self.open(ref) as stream, open(temporary, "wb") as out:
                while block := stream.read(BLOCK_SIZE):
                    out.write(block)
                    if progress:
                        progress(out.tell(), ref.size_bytes)
            with self.cache.lock:
                temporary.replace(path)
                self.cache.db.execute(
                    "INSERT OR REPLACE INTO entries VALUES (?,?,?,?,strftime('%s','now'),1)",
                    (source, source, "files", path.stat().st_size),
                )
                self.cache.db.execute(
                    "UPDATE entries SET pinned=1 WHERE source=? AND category='metadata'", (source,)
                )
                self.cache.db.commit()
                # Full file supersedes disposable range blocks.
                for (id,) in self.cache.db.execute(
                    "SELECT key FROM entries WHERE source=? AND category='ranges'", (source,)
                ).fetchall():
                    self.cache.path("ranges", id).unlink(missing_ok=True)
                    self.cache.db.execute("DELETE FROM entries WHERE key=?", (id,))
                self.cache.db.commit()
            return str(path)
        finally:
            temporary.unlink(missing_ok=True)


class HttpSourceProvider(CachedRemoteProvider):
    def _save_response(self, ref, response, *, pinned=False, progress=None):
        """Narrow compatibility fallback: stream only this selected file to disk."""
        source = source_key(ref)
        path = self.cache.path("files", source)
        path.parent.mkdir(exist_ok=True)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.download")
        transferred = 0
        try:
            with open(temporary, "wb") as out:
                for block in response.iter_bytes(chunk_size=BLOCK_SIZE):
                    out.write(block)
                    transferred += len(block)
                    if progress:
                        progress(transferred, ref.size_bytes)
            if ref.size_bytes is not None and transferred != ref.size_bytes:
                raise OSError("Remote source returned a truncated file")
            with self.cache.lock:
                temporary.replace(path)
                self.cache.db.execute(
                    "INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?)",
                    (source, source, "files", transferred, time.time(), int(pinned)),
                )
                if pinned:
                    self.cache.db.execute(
                        "UPDATE entries SET pinned=1 WHERE source=? AND category='metadata'",
                        (source,),
                    )
                self.cache.db.commit()
            return path
        finally:
            self.cache.transferred_bytes += transferred
            self.cache.requests += 1
            temporary.unlink(missing_ok=True)

    def pin(self, ref, progress=None):
        ref = self.stat(ref).ref
        # Cached range-capable sources reuse all prior reads.
        if self.cache.get_path("files", source_key(ref)):
            return super().pin(ref, progress)
        with httpx.stream(
            "GET",
            ref.uri,
            headers={"Accept-Encoding": "identity"},
            follow_redirects=True,
            timeout=60,
        ) as response:
            response.raise_for_status()
            self._verify_version(ref, response)
            return str(self._save_response(ref, response, pinned=True, progress=progress))

    @staticmethod
    def _verify_version(ref, response):
        current = response.headers.get("etag") or response.headers.get("last-modified")
        if current and ref.etag and current != ref.etag:
            raise OSError("Remote file changed; import a new source version")

    def stat(self, ref):
        if ref.size_bytes is not None and ref.etag:
            return SourceMetadata(
                ref=ref,
                name=ref.uri.rsplit("/", 1)[-1],
                size_bytes=ref.size_bytes,
                is_directory=bool(ref.metadata.get("manifest")),
            )
        cache_id = key(["http-stat", ref.uri, ref.etag])
        cached = self.cache.get("metadata", cache_id)
        if cached:
            return SourceMetadata.model_validate_json(cached)
        response = httpx.head(ref.uri, follow_redirects=True, timeout=30)
        response.raise_for_status()
        size = response.headers.get("content-length")
        ref = ref.model_copy(
            update={
                "size_bytes": int(size) if size else None,
                "etag": response.headers.get("etag") or response.headers.get("last-modified"),
            }
        )
        ref.metadata["lastModified"] = response.headers.get("last-modified")
        if ref.uri.endswith("manifest.json"):
            ref.metadata["manifest"] = True
        value = SourceMetadata(
            ref=ref,
            name=urlparse(ref.uri).path.rsplit("/", 1)[-1],
            size_bytes=ref.size_bytes,
            is_directory=bool(ref.metadata.get("manifest")),
        )
        self.cache.put(
            "metadata", cache_id, value.model_dump_json(by_alias=True).encode(), source_key(ref)
        )
        return value

    def fetch_range(self, ref, start, end):
        headers = {"Range": f"bytes={start}-{end - 1}", "Accept-Encoding": "identity"}
        if ref.etag:
            headers["If-Range"] = ref.etag
        with httpx.stream(
            "GET", ref.uri, headers=headers, follow_redirects=True, timeout=60
        ) as response:
            response.raise_for_status()
            self._verify_version(ref, response)
            if response.status_code != 206:
                path = self._save_response(ref, response)
                with open(path, "rb") as stream:
                    stream.seek(start)
                    result = stream.read(end - start)
                # read_range accounts for the returned block; count the remaining transfer here.
                self.cache.transferred_bytes -= len(result)
                self.cache.requests -= 1
                self.cache.evict()
                return result
            if (
                response.headers.get("content-range", "").split("/")[0]
                != f"bytes {start}-{end - 1}"
            ):
                raise OSError("Server returned a different byte range")
            result = bytearray()
            for block in response.iter_bytes(chunk_size=BLOCK_SIZE):
                result.extend(block)
                if len(result) > end - start:
                    raise OSError("Server exceeded requested byte range")
            return bytes(result)

    def list(self, ref):
        # Deliberate manifest contract, never scrape arbitrary HTML directory pages.
        if not ref.metadata.get("manifest") and not ref.uri.endswith("manifest.json"):
            raise ValueError("HTTP directory listing requires manifest.json with a files array")
        with self.open(ref) as stream:
            raw = stream.read(2 * 1024**2 + 1)
        if len(raw) > 2 * 1024**2:
            raise ValueError("HTTP manifest exceeds 2 MiB")
        from urllib.parse import urljoin

        entries = []
        for item in json.loads(raw).get("files", []):
            item = {"path": item} if isinstance(item, str) else item
            child = source_ref(urljoin(ref.uri, item.get("url", item["path"])))
            child.size_bytes = item.get("sizeBytes")
            child.etag = item.get("etag")
            entries.append(
                SourceEntry(
                    ref=child,
                    name=item["path"].rsplit("/", 1)[-1],
                    path=item["path"],
                    size_bytes=child.size_bytes,
                )
            )
        return entries
