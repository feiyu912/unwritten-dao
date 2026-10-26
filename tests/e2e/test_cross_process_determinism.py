from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECKSUM_RE = re.compile(r"final checksum=(sha256:[0-9a-f]{64})")


def _run(hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.bench_sim",
            "--npcs",
            "30",
            "--years",
            "3",
            "--seed",
            "42",
            "--agent-mode",
            "rules",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    match = CHECKSUM_RE.search(result.stdout)
    assert match is not None, result.stdout[-500:]
    return match.group(1)


def test_checksum_is_stable_across_processes_and_hash_seeds() -> None:
    first = _run("0")
    second = _run("1")
    assert first == second
