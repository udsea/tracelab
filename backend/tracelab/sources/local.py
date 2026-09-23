from pathlib import Path

from tracelab.sources.base import SourceEntry, SourceMetadata, recursive_glob
from tracelab.sources.refs import source_ref


class LocalSourceProvider:
    def stat(self, ref):
        path = Path(ref.uri)
        st = path.stat()
        ref = ref.model_copy(
            update={"size_bytes": st.st_size, "etag": f"{st.st_size}:{st.st_mtime_ns}"}
        )
        return SourceMetadata(
            ref=ref,
            name=path.name,
            is_directory=path.is_dir(),
            size_bytes=st.st_size,
            modified=str(st.st_mtime_ns),
        )

    def list(self, ref):
        return [
            SourceEntry(**self.stat(source_ref(str(path))).wire(), path=str(path))
            for path in sorted(Path(ref.uri).iterdir())
            if not path.is_symlink() and not path.name.startswith(".")
        ]

    def glob(self, ref, pattern):
        return recursive_glob(self, ref, pattern)

    def open(self, ref):
        return open(ref.uri, "rb")

    def read_range(self, ref, start, end):
        with self.open(ref) as stream:
            stream.seek(start)
            return stream.read(max(0, end - start))

    def supports_random_access(self, ref):
        return True
