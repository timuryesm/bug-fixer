"""GitHub API client for the bug fixer.

V1.0a: read-only — fetches issues by URL.
V1.1 will extend this to open pull requests.
"""

import re
from typing import NamedTuple

import requests


ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)/?$"
)


class Issue(NamedTuple):
    """A parsed GitHub issue with everything we need downstream."""

    owner: str
    repo: str
    number: int
    title: str
    body: str
    url: str

    @property
    def repo_clone_url(self) -> str:
        """HTTPS clone URL — works for public repos without auth."""
        return f"https://github.com/{self.owner}/{self.repo}.git"

    def as_bug_description(self) -> str:
        """Format the issue for the LLM fix prompt."""
        return f"Issue title: {self.title}\n\nIssue body:\n{self.body}"


def parse_issue_url(url: str) -> tuple[str, str, int]:
    """Extract (owner, repo, issue_number) from a GitHub issue URL."""
    match = ISSUE_URL_RE.match(url.strip())
    if not match:
        raise ValueError(
            f"Not a valid GitHub issue URL: {url!r}\n"
            f"Expected format: https://github.com/OWNER/REPO/issues/NUMBER"
        )
    return match.group(1), match.group(2), int(match.group(3))


def fetch_issue(url: str, token: str | None = None) -> Issue:
    """Fetch a GitHub issue via the REST API.

    Args:
        url: Full issue URL (e.g. https://github.com/owner/repo/issues/1).
        token: Optional GitHub PAT. Unauthenticated calls work for public
            repos but are rate-limited to 60/hour.

    Returns:
        An Issue with title, body, and metadata.

    Raises:
        ValueError: if the URL isn't a valid issue URL.
        requests.HTTPError: if the API returns a non-2xx status.
    """
    owner, repo, number = parse_issue_url(url)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(api_url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    return Issue(
        owner=owner,
        repo=repo,
        number=number,
        title=data["title"],
        body=data.get("body") or "",
        url=url,
    )