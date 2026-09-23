import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_repository.py"


@pytest.mark.parametrize(
    "name,content,rejected",
    [
        ("src/app.py", "print('example')\n", False),
        ("build/TraceLab/binary", "fixture-binary-payload\n", True),
        (".env.local", "EXAMPLE=true\n", True),
        ("src/config.py", "TOKEN='" + "gh" + "p_" + "A" * 40 + "'\n", True),
    ],
)
def test_repository_policy_checks_index_without_exposing_credentials(
    tmp_path, name, content, rejected
):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "add", name], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER)], cwd=tmp_path, capture_output=True, text=True
    )
    assert (result.returncode != 0) == rejected
    assert content.strip() not in result.stdout + result.stderr
    if rejected:
        assert name in result.stderr
