"""Tests for the execute_python audit-hook sandbox in agent/tools.py.

Run with:
    uv run --directory onc-data-wrangler-plugin pytest tests/test_execute_python_sandbox.py -v
"""
import os
import tempfile
from pathlib import Path

import pytest

from onc_wrangler.agent.tools import execute_python


@pytest.fixture
def sandbox_env():
    """Create an allowed data dir (with a CSV), a forbidden dir (with a 'paper'),
    and a work dir. Returns dict of paths."""
    with tempfile.TemporaryDirectory(prefix="sbx_test_") as root:
        root_p = Path(root)
        allowed = root_p / "allowed"
        forbidden = root_p / "forbidden"
        work = root_p / "work"
        allowed.mkdir()
        forbidden.mkdir()
        work.mkdir()
        (allowed / "data.csv").write_text("a,b\n1,2\n3,4\n")
        (forbidden / "paper.txt").write_text("SECRET_PAPER_CONTENT_XYZ")
        yield {
            "root": str(root_p),
            "allowed": str(allowed),
            "forbidden": str(forbidden),
            "forbidden_file": str(forbidden / "paper.txt"),
            "allowed_file": str(allowed / "data.csv"),
            "work": str(work),
        }


def test_allowed_file_read_succeeds(sandbox_env):
    code = f"""
with open({sandbox_env['allowed_file']!r}) as f:
    print("OK", f.read().strip())
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "OK" in out
    assert "1,2" in out


def test_forbidden_file_read_blocked(sandbox_env):
    code = f"""
try:
    with open({sandbox_env['forbidden_file']!r}) as f:
        print("LEAK:", f.read())
except PermissionError as e:
    print("BLOCKED:", str(e)[:80])
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "BLOCKED" in out
    assert "SECRET_PAPER_CONTENT_XYZ" not in out
    assert "LEAK" not in out


def test_forbidden_unhandled_propagates(sandbox_env):
    """If the worker does not catch the PermissionError, the subprocess exits
    non-zero and the secret never appears in output."""
    code = f"open({sandbox_env['forbidden_file']!r}).read()\n"
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "SECRET_PAPER_CONTENT_XYZ" not in out
    assert "SANDBOX" in out
    assert "[Exit code" in out


def test_subprocess_spawn_blocked(sandbox_env):
    """Blocks cat paper.txt via subprocess."""
    code = f"""
import subprocess
try:
    r = subprocess.run(["cat", {sandbox_env['forbidden_file']!r}], capture_output=True, text=True)
    print("LEAK:", r.stdout)
except PermissionError as e:
    print("BLOCKED:", str(e)[:80])
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "SECRET_PAPER_CONTENT_XYZ" not in out
    assert "BLOCKED" in out
    assert "LEAK" not in out


def test_os_exec_blocked(sandbox_env):
    code = f"""
import os
try:
    os.execv("/bin/cat", ["cat", {sandbox_env['forbidden_file']!r}])
except PermissionError as e:
    print("BLOCKED:", str(e)[:80])
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "BLOCKED" in out
    assert "SECRET_PAPER_CONTENT_XYZ" not in out


def test_pandas_import_and_read_csv_still_works(sandbox_env):
    """Regression: sandbox must not break normal analysis workflow."""
    code = f"""
import pandas as pd
df = pd.read_csv({sandbox_env['allowed_file']!r})
print("SHAPE", df.shape)
print("SUM", int(df.sum().sum()))
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "SHAPE (2, 2)" in out
    assert "SUM 10" in out


def test_write_to_work_dir_allowed(sandbox_env):
    """Workers must be able to write JSON output to the work dir."""
    out_path = os.path.join(sandbox_env["work"], "result.json")
    code = f"""
import json
with open({out_path!r}, "w") as f:
    json.dump({{"answer": 42}}, f)
print("WROTE", {out_path!r})
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "WROTE" in out
    assert os.path.exists(out_path)
    import json as _json
    assert _json.loads(open(out_path).read())["answer"] == 42


def test_write_outside_allowed_blocked(sandbox_env):
    """Workers cannot smuggle data out by writing into the forbidden dir."""
    evil = os.path.join(sandbox_env["forbidden"], "stolen.txt")
    code = f"""
try:
    with open({evil!r}, "w") as f:
        f.write("hi")
    print("LEAK")
except PermissionError as e:
    print("BLOCKED", str(e)[:60])
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=[sandbox_env["allowed"], sandbox_env["work"]],
    )
    assert "BLOCKED" in out
    assert "LEAK" not in out
    assert not os.path.exists(evil)


def test_sandbox_disabled_when_allowed_dirs_is_none(sandbox_env):
    """Backwards compat: allowed_dirs=None skips the sandbox entirely."""
    code = f"""
with open({sandbox_env['forbidden_file']!r}) as f:
    print("READ", f.read())
"""
    out = execute_python(
        code=code,
        work_dir=sandbox_env["work"],
        allowed_dirs=None,
    )
    assert "SECRET_PAPER_CONTENT_XYZ" in out
