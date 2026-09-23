"""Fail CI if generated bundles, local data, or recognizable secrets enter the Git index.

This is a lightweight last line of defense, not a comprehensive secret scanner.
Only filenames and finding categories are printed; secret values are never logged.
"""

import re
import subprocess
import sys
from pathlib import PurePosixPath

GENERATED = {
    "node_modules",
    "dist",
    "build",
    "target",
    "binaries",
    "gen",
    "artifacts",
    ".venv",
    "venv",
    "__pycache__",
    ".tracelab",
    ".cache",
    ".pnpm-store",
}
EXTENSIONS = {
    ".dmg",
    ".exe",
    ".msi",
    ".appimage",
    ".deb",
    ".rpm",
    ".zip",
    ".eval",
    ".duckdb",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
PATTERNS = {
    "private key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "GitHub token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "provider token": rb"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}|hf_[A-Za-z0-9]{25,})\b",
    "AWS access key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
}


def main():
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"]).split(b"\0")
    problems = []
    count = 0
    for entry in filter(None, entries):
        header, raw_name = entry.split(b"\t", 1)
        mode, oid, stage = header.split()
        name = raw_name.decode()
        path = PurePosixPath(name)
        count += 1
        if stage != b"0":
            problems.append((name, "unresolved merge conflict"))
        if mode not in (b"100644", b"100755"):
            problems.append((name, "review required for symlink or submodule"))
            continue
        if (
            set(path.parts) & GENERATED
            or path.suffix.lower() in EXTENSIONS
            or name.endswith(".tar.gz")
        ):
            problems.append((name, "generated build, local data, or credential file"))
        if path.name.startswith(".env") and path.name != ".env.example":
            problems.append((name, "local environment file"))
        value = subprocess.check_output(["git", "cat-file", "blob", oid.decode()])
        if len(value) > 5 * 1024**2:
            problems.append(
                (name, "file exceeds 5 MiB; use an external test corpus or CI artifact")
            )
        for label, pattern in PATTERNS.items():
            if re.search(pattern, value):
                problems.append((name, label))
    for name, reason in problems:
        print(f"{name}: {reason}", file=sys.stderr)
    print(f"Repository policy: {count} indexed files, {len(problems)} findings")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
