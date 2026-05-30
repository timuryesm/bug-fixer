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


import os


def create_branch_and_commit(
    repo_path: Path,
    branch_name: str,
    commit_message: str,
    author_name: str = "bug-fixer",
    author_email: str = "bug-fixer@local",
) -> None:
    """Create a branch from current state, stage all changes, commit as bug-fixer."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=repo_path, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_path, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=repo_path, check=True, capture_output=True, text=True, env=env,
    )


def push_branch(
    repo_path: Path,
    branch_name: str,
    owner: str,
    repo: str,
    token: str,
) -> None:
    """Push branch_name to GitHub using the token for HTTPS auth."""
    push_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    result = subprocess.run(
        ["git", "push", push_url, branch_name],
        cwd=repo_path, capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Hide the token from any error output we might show
        safe_err = result.stderr.replace(token, "***")
        raise RuntimeError(f"git push failed:\n{safe_err}")