from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPT = (
    "go 山间破庙; take 残破洞府图; go 迷雾谷; investigate; "
    "go 无名古修洞府; claim 洞府丹藏; look; quit"
)


def test_play_cli_script_reaches_the_pill() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tools.play", "--script", SCRIPT],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "claimed" in result.stdout
    assert "筑基丹" in result.stdout
    assert "checksum=sha256:" in result.stdout
