from __future__ import annotations

import fnmatch
import io
from typing import BinaryIO, Protocol

from tracelab.models.domain import AppModel, SourceRef


class SourceMetadata(AppModel):
    ref: SourceRef
    name: str
    is_directory: bool = False
    size_bytes: int | None = None
    modified: str | None = None


class SourceEntry(SourceMetadata):
    path: str
    format_hint: str | None = None
    cached_bytes: int = 0


class SourceProvider(Protocol):
    def stat(self, ref: SourceRef) -> SourceMetadata: ...
    def list(self, ref: SourceRef) -> list[SourceEntry]: ...
    def glob(self, ref: SourceRef, pattern: str) -> list[SourceEntry]: ...
    def open(self, ref: SourceRef) -> BinaryIO: ...
    def read_range(self, ref: SourceRef, start: int, end: int) -> bytes: ...
    def supports_random_access(self, ref: SourceRef) -> bool: ...


class RangeReader(io.RawIOBase):
    """Seekable bounded-block reader. end offsets are exclusive."""

    def __init__(self, provider, ref, size):
        self.provider, self.ref, self.size, self.position = provider, ref, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        target = (
            offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        )
        if target < 0:
            raise ValueError("Negative seek")
        self.position = target
        return target

    def readinto(self, buffer):
        value = self.read(len(buffer))
        buffer[: len(value)] = value
        return len(value)

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.size, self.position + size)
        if end <= self.position:
            return b""
        value = self.provider.read_range(self.ref, self.position, end)
        self.position += len(value)
        return value


def recursive_glob(provider, ref, pattern):
    result = []
    for entry in provider.list(ref):
        if entry.is_directory:
            result.extend(recursive_glob(provider, entry.ref, pattern))
        elif fnmatch.fnmatch(entry.path, pattern) or fnmatch.fnmatch(entry.name, pattern):
            result.append(entry)
    return result
