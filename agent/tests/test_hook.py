"""The PreToolUse-style shell hook, run with stand-in `fineprint` executables."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "fineprint-pre-python.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def fake_bin(tmp_path, code, out="| table |"):
    p = tmp_path / "fineprint"
    p.write_text(f"#!/usr/bin/env bash\necho '{out}'\necho \"$@\" > '{tmp_path}/args'\nexit {code}\n")
    p.chmod(0o755)
    return p


def run(command, env):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", **env}, timeout=30)


@pytest.mark.parametrize("cmd", ["python train.py", "uv run train.py", "cd x && python3 -m pkg", "pytest -q"])
def test_blocks_python_when_clouded(tmp_path, cmd):
    r = run(cmd, {"FINEPRINT_BIN": str(fake_bin(tmp_path, 1))})
    assert r.returncode == 2
    assert "| table |" in r.stderr and "FINEPRINT_ALLOW" in r.stderr


def test_ignores_non_python_commands(tmp_path):
    r = run("ls -la && git status", {"FINEPRINT_BIN": str(fake_bin(tmp_path, 1))})
    assert r.returncode == 0
    assert not (tmp_path / "args").exists()


def test_clean_and_unreachable_let_command_run(tmp_path):
    assert run("python a.py", {"FINEPRINT_BIN": str(fake_bin(tmp_path, 0))}).returncode == 0
    r = run("python a.py", {"FINEPRINT_BIN": str(fake_bin(tmp_path, 3))})
    assert r.returncode == 0 and "not reachable" in r.stderr


def test_strict_flag_and_path(tmp_path):
    run("python a.py", {"FINEPRINT_BIN": str(fake_bin(tmp_path, 0)), "FINEPRINT_HOOK_STRICT": "1",
                        "FINEPRINT_HOOK_PATH": "/some/repo"})
    assert (tmp_path / "args").read_text().split() == ["check", "/some/repo", "--strict"]


def test_missing_binary_fails_open(tmp_path):
    r = run("python a.py", {"FINEPRINT_BIN": str(tmp_path / "nope")})
    assert r.returncode == 0 and "not found" in r.stderr


def test_bad_json_is_ignored(tmp_path):
    r = subprocess.run(["bash", str(HOOK)], input="not json", capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "FINEPRINT_BIN": str(fake_bin(tmp_path, 1))}, timeout=30)
    assert r.returncode == 0


def test_fail_closed_blocks_when_check_cannot_run(tmp_path):
    env = {"FINEPRINT_FAIL_CLOSED": "1"}
    r = run("python a.py", {**env, "FINEPRINT_BIN": str(fake_bin(tmp_path, 3))})
    assert r.returncode == 2 and "FINEPRINT_FAIL_CLOSED" in r.stderr
    r = run("python a.py", {**env, "FINEPRINT_BIN": str(tmp_path / "nope")})
    assert r.returncode == 2 and "not found" in r.stderr
    r = run("python a.py", {**env, "FINEPRINT_BIN": str(fake_bin(tmp_path, 70))})
    assert r.returncode == 2
    assert run("python a.py", {**env, "FINEPRINT_BIN": str(fake_bin(tmp_path, 0))}).returncode == 0


def test_fail_open_warning(tmp_path):
    r = run("python a.py", {"FINEPRINT_BIN": str(fake_bin(tmp_path, 3))})
    assert r.returncode == 0
    assert "WARNING" in r.stderr and "FINEPRINT_FAIL_CLOSED=1" in r.stderr


def test_fail_closed_end_to_end_with_real_cli(tmp_path):
    """Real `fineprint` CLI, API on a closed port: open lets it run, closed blocks."""
    import sys
    exe = Path(sys.executable).with_name("fineprint")
    if not exe.exists():
        pytest.skip("fineprint script not installed next to this python")
    (tmp_path / "a.py").write_text('from_pretrained("Qwen/Qwen2.5-7B-Instruct")\n')
    env = {"FINEPRINT_BIN": str(exe), "FINEPRINT_API": "http://127.0.0.1:9", "FINEPRINT_HOOK_PATH": str(tmp_path)}
    assert run("python a.py", env).returncode == 0
    r = run("python a.py", {**env, "FINEPRINT_FAIL_CLOSED": "1"})
    assert r.returncode == 2 and "fail-closed" in r.stderr
