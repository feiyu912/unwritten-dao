from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPT = (
    "go 山间破庙; take 残破洞府图; go 迷雾谷; investigate; "
    "go 无名古修洞府; " + "; ".join(["claim 洞府丹藏"] * 10) + "; look; quit"
)


def test_play_cli_script_reaches_the_pill() -> None:
    # The CLI prints Chinese text: force the child's stdio to UTF-8 and decode
    # the pipes as UTF-8 instead of the Windows locale code page (cp936).
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-m", "tools.play", "--script", SCRIPT],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "claimed" in result.stdout
    assert "筑基丹" in result.stdout
    assert "checksum=sha256:" in result.stdout
    assert "结局：" in result.stdout
    assert "pill_held" in result.stdout
    assert "realm_found" in result.stdout
