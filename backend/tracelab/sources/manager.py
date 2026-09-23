from tracelab.sources.cache import RemoteCache
from tracelab.sources.huggingface import HuggingFaceSourceProvider
from tracelab.sources.local import LocalSourceProvider
from tracelab.sources.refs import source_ref
from tracelab.sources.remote import HttpSourceProvider


class Sources:
    def __init__(self, root):
        self.cache = RemoteCache(root)
        self.providers = {
            "local": LocalSourceProvider(),
            "huggingface": HuggingFaceSourceProvider(self.cache),
            "http": HttpSourceProvider(self.cache),
        }

    def provider(self, ref):
        return self.providers[ref.kind]

    def resolve(self, value, **kwargs):
        ref = source_ref(value, **kwargs)
        return self.provider(ref).stat(ref)

    def close(self):
        self.cache.close()

    def stat(self, ref):
        return self.provider(ref).stat(ref)

    def list(self, ref):
        return self.provider(ref).list(ref)

    def glob(self, ref, pattern):
        return self.provider(ref).glob(ref, pattern)

    def open(self, ref):
        return self.provider(ref).open(ref)

    def read_range(self, ref, start, end):
        return self.provider(ref).read_range(ref, start, end)

    def supports_random_access(self, ref):
        return self.provider(ref).supports_random_access(ref)
