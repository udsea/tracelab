from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from tracelab.models.domain import SourceRef


def source_ref(value: str | dict | SourceRef, kind=None, repo_type="dataset", revision="main"):
    if isinstance(value, SourceRef):
        return value
    if isinstance(value, dict):
        return SourceRef.model_validate(value)
    value = value.strip()
    parsed = urlparse(value)
    if (
        value.startswith("hf://")
        or parsed.hostname in ("huggingface.co", "www.huggingface.co")
        or kind == "huggingface"
    ):
        path = (
            value[5:]
            if value.startswith("hf://")
            else parsed.path.lstrip("/")
            if parsed.scheme
            else value
        )
        parts = path.split("/")
        if (value.startswith("hf://") or parsed.hostname) and parts[0] not in (
            "datasets",
            "spaces",
            "models",
        ):
            repo_type = "model"
        repo_type = {"datasets": "dataset", "spaces": "space", "models": "model"}.get(
            parts[0], repo_type
        )
        if parts[0] in ("datasets", "spaces", "models"):
            parts.pop(0)
        if len(parts) < 2 or not all(parts[:2]):
            raise ValueError("Enter a Hugging Face repository as owner/name")
        repo = "/".join(parts[:2])
        rest = parts[2:]
        if "@" in repo:
            repo, revision = repo.rsplit("@", 1)
            revision = unquote(revision)
        if rest and rest[0] in ("blob", "resolve", "tree"):
            if len(rest) < 2:
                raise ValueError("Hugging Face URL is missing its revision")
            revision, rest = unquote(rest[1]), rest[2:]
        inner = unquote("/".join(rest)).strip("/")
        if ".." in inner.split("/"):
            raise ValueError("Invalid repository path")
        prefix = {"dataset": "datasets/", "space": "spaces/", "model": ""}[repo_type]
        uri = f"hf://{prefix}{repo}@{quote(revision, safe='')}/{inner}".rstrip("/")
        return SourceRef(
            kind="huggingface",
            uri=uri,
            revision=revision,
            metadata={
                "repoId": repo,
                "repoType": repo_type,
                "path": inner,
                "requestedRevision": revision,
            },
        )
    if parsed.scheme in ("http", "https"):
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "Use a stable HTTP URL without embedded credentials, query, or fragment; HF authentication uses the local Hub token"
            )
        return SourceRef(kind="http", uri=value)
    path = Path(unquote(parsed.path) if parsed.scheme == "file" else value).expanduser().resolve()
    return SourceRef(kind="local", uri=str(path))


def hf_url(ref, *, raw=False):
    meta = ref.metadata
    prefix = {"dataset": "datasets/", "space": "spaces/", "model": ""}[meta["repoType"]]
    base = f"https://huggingface.co/{prefix}{meta['repoId']}"
    return f"{base}/{'resolve' if raw else 'blob'}/{quote(ref.revision or 'main', safe='')}/{quote(meta.get('path', ''), safe='/')}"


def child_ref(ref, path):
    if ref.kind == "huggingface":
        child = ref.model_copy(deep=True)
        child.metadata["path"] = path
        child.uri = (
            ref.uri.split("@", 1)[0] + "@" + quote(ref.revision or "main", safe="") + "/" + path
        )
        child.size_bytes = None
        child.etag = None
        child.checksum = None
        return child
    if ref.kind == "local":
        return source_ref(str(Path(ref.uri) / path))
    from urllib.parse import urljoin

    return source_ref(urljoin(ref.uri, path))
