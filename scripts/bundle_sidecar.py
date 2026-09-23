"""Build a self-contained Python runtime for Tauri's resource bundle."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name",
        "tracelab-backend",
        "--paths",
        str(ROOT / "backend"),
        "--collect-all",
        "inspect_ai",
        "--collect-all",
        "duckdb",
        "--collect-all",
        "tiktoken",
        "--collect-submodules",
        "tracelab",
        "--collect-all",
        "textual",
        "--collect-all",
        "rich",
        "--collect-all",
        "huggingface_hub",
        "--collect-all",
        "ijson",
        "--collect-submodules",
        "fsspec",
        "--copy-metadata",
        "inspect-ai",
        "--hidden-import",
        "openai",
        "--hidden-import",
        "anthropic",
        "--distpath",
        str(ROOT / "build" / "sidecar"),
        str(ROOT / "scripts" / "sidecar_entry.py"),
    ],
    cwd=ROOT,
    check=True,
    env={
        **os.environ,
        "PYINSTALLER_CONFIG_DIR": str(ROOT / "build" / "pyinstaller-cache"),
    },
)
target = ROOT / "src-tauri" / "binaries" / "tracelab-backend"
if target.exists():
    shutil.rmtree(target)
shutil.copytree(ROOT / "build" / "sidecar" / "tracelab-backend", target)
print(f"Sidecar ready: {target}")
