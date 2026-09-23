import io
from types import SimpleNamespace

import pytest
from tracelab.sources.cache import RemoteCache, key, source_key
from tracelab.sources.huggingface import HuggingFaceSourceProvider
from tracelab.sources.refs import source_ref


@pytest.mark.parametrize(
    "value",
    [
        "hf://datasets/org/repo@main/a.jsonl",
        "https://huggingface.co/datasets/org/repo/blob/main/a.jsonl",
        "https://huggingface.co/datasets/org/repo/resolve/main/a.jsonl",
        "https://huggingface.co/datasets/org/repo/tree/main/a.jsonl",
    ],
)
def test_hf_reference_normalization(value):
    ref = source_ref(value)
    assert ref.metadata == {
        "repoId": "org/repo",
        "repoType": "dataset",
        "path": "a.jsonl",
        "requestedRevision": "main",
    }
    assert ref.uri == "hf://datasets/org/repo@main/a.jsonl"


class FakeHub:
    sha = "a" * 40

    def repo_info(self, *args, **kwargs):
        return SimpleNamespace(sha=self.sha)

    def list_repo_tree(self, *args, **kwargs):
        return [SimpleNamespace(path="trace.jsonl", size=200000, blob_id="blob", lfs=None)]

    def get_paths_info(self, *args, **kwargs):
        return self.list_repo_tree()


class MeasuredFS:
    def __init__(self, value):
        self.value, self.bytes, self.offline = value, 0, False

    def open(self, *args, **kwargs):
        if self.offline:
            raise OSError("offline")
        owner = self

        class Stream(io.BytesIO):
            def read(self, size=-1):
                value = super().read(size)
                owner.bytes += len(value)
                return value

        assert kwargs["cache_type"] == "none"
        return Stream(self.value)


def test_hf_listing_is_metadata_only_ranges_cache_pin_and_offline(tmp_path):
    cache = RemoteCache(tmp_path)
    fs = MeasuredFS(b"x" * 200000)
    provider = HuggingFaceSourceProvider(cache, FakeHub(), fs)
    root = provider.resolve(source_ref("org/repo", kind="huggingface"))
    entries = provider.list(root)
    assert fs.bytes == cache.transferred_bytes == 0
    ref = entries[0].ref
    assert ref.revision == "a" * 40
    assert provider.read_range(ref, 50, 100) == b"x" * 50
    assert fs.bytes == 65536
    provider.read_range(ref, 100, 200)
    assert fs.bytes == 65536
    fs.offline = True
    assert provider.read_range(ref, 10, 100) == b"x" * 90
    with pytest.raises(OSError, match="cached"):
        provider.read_range(ref, 100000, 100010)
    fs.offline = False
    provider.pin(ref)
    assert fs.bytes == 200000
    fs.offline = True
    cache.clear()  # pinned file survives
    with provider.open(ref) as stream:
        assert len(stream.read()) == 200000
    assert cache.stats(source_key(ref))["pinnedBytes"] == 200000
    cache.close()
    reopened = RemoteCache(tmp_path)
    provider = HuggingFaceSourceProvider(reopened, FakeHub(), fs)
    assert len(provider.read_range(ref, 0, 200000)) == 200000
    reopened.close()


def test_new_revision_is_a_distinct_cache_identity(tmp_path):
    cache = RemoteCache(tmp_path)
    hub = FakeHub()
    provider = HuggingFaceSourceProvider(cache, hub, MeasuredFS(b""))
    old = provider.resolve(source_ref("org/repo", kind="huggingface"), fresh=True)
    hub.sha = "b" * 40
    new = provider.resolve(source_ref("org/repo", kind="huggingface"), fresh=True)
    assert old.revision != new.revision
    assert source_key(old) != source_key(new)
    cache.close()


def test_cache_lru_never_evicts_pins(tmp_path):
    cache = RemoteCache(tmp_path)
    cache.configure(16 * 1024**2)
    cache.put("files", key("pin"), b"x" * (10 * 1024**2), pinned=True)
    cache.put("ranges", key("old"), b"y" * (5 * 1024**2))
    cache.put("ranges", key("new"), b"z" * (5 * 1024**2))
    assert cache.get("ranges", key("old")) is None
    assert cache.get_path("files", key("pin"))
    assert cache.get_path("ranges", key("new"))
    cache.close()
