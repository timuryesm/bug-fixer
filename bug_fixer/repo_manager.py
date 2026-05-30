"""Local repository management: clone targets, clean up."""

import shutil
import subprocess
import tempfile
from pathlib import Path


def clone_to_temp(clone_url: str) -> Path:
    """Clone a repo into a fresh temp directory. Returns the path."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="bug_fixer_"))
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(tmp_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"git clone failed:\n{exc.stderr}") from exc
    return tmp_dir


def cleanup(path: Path) -> None:
    """Remove a directory tree. Safe to call on missing paths."""
    shutil.rmtree(path, ignore_errors=True)