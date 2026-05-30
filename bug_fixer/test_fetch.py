"""Quick sanity check that the GitHub client works.

Usage:
    python -m bug_fixer.test_fetch <issue_url>

Doesn't touch the fixer or LLM — just fetches and prints.
"""

import os
import sys

from bug_fixer.github_client import fetch_issue


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m bug_fixer.test_fetch <github_issue_url>")

    url = sys.argv[1]
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("⚠️  GITHUB_TOKEN not set — using unauthenticated access (60/hr limit)")

    issue = fetch_issue(url, token=token)
    print(f"📄 Issue #{issue.number} in {issue.owner}/{issue.repo}")
    print(f"   Title: {issue.title}")
    print(f"   Clone URL: {issue.repo_clone_url}")
    print(f"\n--- Body ---\n{issue.body}")
    print(f"\n--- As bug description for LLM ---\n{issue.as_bug_description()}")


if __name__ == "__main__":
    main()