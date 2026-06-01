"""Sandboxed test execution via Docker.

Encapsulates the `docker run` subprocess plumbing so the rest of bug_fixer
doesn't need to know about container internals.
"""

import shutil
import subprocess
from pathlib import Path


SANDBOX_IMAGE = "bug-fixer-sandbox"


def check_docker_available() -> tuple[bool, str]:
    """Return (ok, error_message). True if docker CLI is on PATH and the daemon is reachable."""
    if not shutil.which("docker"):
        return False, "docker command not found on PATH. Install Docker Desktop and try again."

    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return False, "docker daemon not reachable. Is Docker Desktop running?"
    return True, ""


def image_exists(image: str) -> bool:
    """Return True if a Docker image with the given tag exists locally."""
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def build_image(image: str, dockerfile_dir: Path) -> None:
    """Build the sandbox image from the Dockerfile in dockerfile_dir."""
    result = subprocess.run(
        ["docker", "build", "-t", image, str(dockerfile_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to build sandbox image '{image}':\n{result.stderr}"
        )


def run_tests_in_sandbox(
    repo_path: Path,
    image: str = SANDBOX_IMAGE,
    setup_cmd: str | None = None,
) -> tuple[bool, str]:
    """Run pytest inside a Docker container with repo_path mounted at /work.

    Args:
        repo_path: Absolute path to the target repo on the host.
        image: Docker image tag to use as the sandbox.
        setup_cmd: Optional shell command to run before pytest
            (e.g. "pip install -e ." or "pip install -r requirements.txt").

    Returns:
        (all_passed, combined_output) — same shape as the host run_tests.
    """
    if setup_cmd:
        # Chain setup + pytest in a shell. Setup output is silenced so it
        # doesn't pollute the pytest output our parser depends on.
        inner_cmd = ["sh", "-c", f"{setup_cmd} > /dev/null 2>&1; pytest -v"]
    else:
        inner_cmd = ["pytest", "-v"]

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{repo_path}:/work",
        image,
    ] + inner_cmd

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout + result.stderr