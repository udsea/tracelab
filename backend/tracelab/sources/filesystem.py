"""Public fsspec bridge used by Inspect's public log readers, not an .eval decoder."""

from uuid import uuid4

import fsspec
from fsspec.spec import AbstractFileSystem


class TraceLabFileSystem(AbstractFileSystem):
    protocol = "tracelab"
    cachable = False
    sources = {}

    def _open(self, path, mode="rb", **kwargs):
        if mode != "rb":
            raise ValueError("TraceLab sources are read-only")
        provider, ref = self.sources[self._strip_protocol(path)]
        return provider.open(ref)

    def info(self, path, **kwargs):
        provider, ref = self.sources[self._strip_protocol(path)]
        item = provider.stat(ref)
        return {"name": path, "size": item.size_bytes, "type": "file", "mtime": item.modified}

    @classmethod
    def bind(cls, provider, ref):
        name = uuid4().hex + ("/source.json" if ref.uri.endswith(".json") else "/source.eval")
        cls.sources[name] = (provider, ref)
        return "tracelab://" + name

    @classmethod
    def release(cls, uri):
        cls.sources.pop(cls._strip_protocol(uri), None)


fsspec.register_implementation("tracelab", TraceLabFileSystem, clobber=True)
