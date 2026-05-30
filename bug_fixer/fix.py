"""V1 Bug Fixer.

Inputs:
- A natural-language bug description (--bug), OR a GitHub issue URL (--issue),
  or both.
- A local repo path (--repo), OR the issue's repo will be cloned automatically.

Pipeline:
1. Fetch issue (if --issue).
2. Clone target repo (if --repo not provided).
3. Run tests, record passing/failing sets.
4. Ask the LLM for a patch.
5. Reject syntactically invalid patches before any disk write.
6. Apply patch, re-run tests.
7. Keep the patch only if it's regression-free and made progress.
"""

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

from bug_fixer.github_client import Issue, fetch_issue
from bug_fixer.repo_manager import clone_to_temp, cleanup


SYSTEM_PROMPT = """You are an expert Python developer fixing bugs in a small codebase.

You will be given:
1. A bug description (often from a failing test or an issue report).
2. The full contents of one or more source files from the codebase.

Your job: identify the bug and return a fixed version of the single file that
contains the bug.

You MUST respond in EXACTLY this format, with no extra text before or after:

REASONING: <1-3 sentences explaining what the bug is and how you're fixing it>
FILE: <exact relative path of the file you are modifying>
```python
<complete new content of that file, exactly as it should appear on disk>
```

Rules:
- Only modify ONE file per fix.
- Return the COMPLETE new file content inside the code fence, not a diff.
- Preserve all unrelated code, comments, and docstrings exactly.
- Do not introduce new dependencies or imports unless strictly necessary.
"""


def read_source_files(repo_path: Path) -> dict[str, str]:
    """Read all non-__init__ .py files under src/. Returns {relative_path: content}."""
    files: dict[str, str] = {}
    src_dir = repo_path / "src"
    if not src_dir.is_dir():
        return files
    for py_file in sorted(src_dir.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        rel_path = py_file.relative_to(repo_path)
        files[str(rel_path)] = py_file.read_text()
    return files


def build_user_prompt(bug_description: str, files: dict[str, str]) -> str:
    parts = [f"Bug description:\n{bug_description}\n", "Source files:"]
    for path, content in files.items():
        parts.append(f"\n--- {path} ---\n{content}")
    return "\n".join(parts)


def parse_llm_response(text: str) -> dict:
    """Parse reasoning, file_path, new_content from the LLM response."""
    file_match = re.search(r"FILE:\s*(\S+)", text)
    if not file_match:
        raise ValueError(f"No 'FILE:' marker found in LLM response:\n{text[:500]}")

    reasoning_match = re.search(r"REASONING:\s*(.+?)\s*FILE:", text, re.DOTALL)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else "(none)"

    code_match = re.search(r"```(?:python\s*)?(.*?)```", text, re.DOTALL)
    if not code_match:
        raise ValueError(f"No code fence found in LLM response:\n{text[:500]}")

    return {
        "reasoning": reasoning,
        "file_path": file_match.group(1).strip(),
        "new_content": code_match.group(1).strip("\n"),
    }


def call_llm(client: OpenAI, system_prompt: str, user_prompt: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return parse_llm_response(response.choices[0].message.content)


def is_valid_python(source: str) -> tuple[bool, str]:
    """Return (ok, error_message). Checks that source parses as Python."""
    try:
        ast.parse(source)
        return True, ""
    except SyntaxError as exc:
        return False, f"{exc.msg} at line {exc.lineno}"


def apply_patch(repo_path: Path, file_path: str, new_content: str) -> Path:
    """Write new_content to repo_path/file_path. Return path to the .bak backup."""
    target = repo_path / file_path
    if not target.exists():
        raise FileNotFoundError(f"File to patch does not exist: {target}")
    backup = target.with_suffix(target.suffix + ".bak")
    shutil.copy2(target, backup)
    target.write_text(new_content)
    return backup


def restore_backup(target: Path, backup: Path) -> None:
    shutil.move(str(backup), str(target))


def run_tests(repo_path: Path) -> tuple[bool, str]:
    """Run pytest in repo_path. Return (all_passed, combined_output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stdout + result.stderr


def last_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def parse_test_results(output: str) -> tuple[set[str], set[str]]:
    """Parse `pytest -v` output into (passing, failing) sets of test IDs."""
    passing: set[str] = set()
    failing: set[str] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        test_id, status = parts[0], parts[1]
        if "::" not in test_id:
            continue
        if status == "PASSED":
            passing.add(test_id)
        elif status in {"FAILED", "ERROR"}:
            failing.add(test_id)
    return passing, failing


def run_fix(
    client: OpenAI,
    repo_path: Path,
    bug_description: str,
    keep_fix: bool,
) -> None:
    """Run the fix loop against a local repo."""
    print(f"\n📂 Reading source files from {repo_path}/src ...")
    files = read_source_files(repo_path)
    if not files:
        sys.exit("No source files found under src/.")
    print(f"   Found {len(files)} file(s): {', '.join(files.keys())}")

    print("\n🧪 Running tests BEFORE fix ...")
    _, pre_output = run_tests(repo_path)
    print(f"   {last_line(pre_output)}")

    print("\n🤖 Asking LLM for a fix ...")
    user_prompt = build_user_prompt(bug_description, files)
    try:
        result = call_llm(client, SYSTEM_PROMPT, user_prompt)
    except Exception as exc:
        sys.exit(f"LLM call failed: {exc}")

    file_path = result.get("file_path")
    new_content = result.get("new_content")
    reasoning = result.get("reasoning", "(no reasoning provided)")
    if not file_path or new_content is None:
        sys.exit(f"LLM response missing required fields: {result}")

    print(f"\n💡 LLM reasoning: {reasoning}")
    print(f"   Patching file: {file_path}")

    ok, err = is_valid_python(new_content)
    if not ok:
        print(f"\n❌ LLM produced invalid Python: {err}")
        print("   Refusing to apply the patch. Original file unchanged.")
        sys.exit(1)

    target = repo_path / file_path
    backup = apply_patch(repo_path, file_path, new_content)

    print("\n🧪 Running tests AFTER fix ...")
    _, post_output = run_tests(repo_path)
    print(f"   {last_line(post_output)}")

    pre_pass, pre_fail = parse_test_results(pre_output)
    post_pass, post_fail = parse_test_results(post_output)

    pre_all = pre_pass | pre_fail
    post_all = post_pass | post_fail
    missing_tests = pre_all - post_all

    newly_passing = pre_fail - post_fail
    new_failures = post_fail - pre_fail

    def _revert_or_keep() -> None:
        if keep_fix:
            print(f"   Keeping patched file. Backup at {backup}.")
        else:
            print(f"   Reverting {file_path} from backup.")
            restore_backup(target, backup)

    if missing_tests:
        print(
            f"\n❌ Catastrophic: {len(missing_tests)} test(s) did not run "
            "after the patch (likely a syntax error or broken import):"
        )
        for t in sorted(missing_tests):
            print(f"   - {t}")
        _revert_or_keep()
        print("\n--- Test output ---")
        print(post_output)
    elif new_failures:
        print(f"\n❌ Regression: {len(new_failures)} previously passing test(s) now fail:")
        for t in sorted(new_failures):
            print(f"   - {t}")
        _revert_or_keep()
    elif not newly_passing:
        print("\n❌ Fix had no effect: no previously failing tests now pass.")
        _revert_or_keep()
    else:
        print(f"\n✅ Fix successful: {len(newly_passing)} test(s) now pass:")
        for t in sorted(newly_passing):
            print(f"   - {t}")
        if post_fail:
            print(
                f"   ({len(post_fail)} other test(s) still failing — "
                "likely unrelated bugs.)"
            )
        backup.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="V1 Bug Fixer")
    parser.add_argument(
        "--repo",
        help="Path to local target repo. If omitted, the issue's repo is cloned.",
    )
    parser.add_argument(
        "--bug",
        help="Bug description (natural language). Overrides --issue body if both given.",
    )
    parser.add_argument(
        "--issue",
        help="GitHub issue URL. The issue body becomes the bug description; "
        "the issue's repo is cloned automatically if --repo is omitted.",
    )
    parser.add_argument(
        "--keep-fix",
        action="store_true",
        help="Keep the patched file even if tests fail (for inspection)",
    )
    parser.add_argument(
        "--keep-clone",
        action="store_true",
        help="Don't delete the temporary clone when done (for inspection)",
    )
    args = parser.parse_args()

    if not args.bug and not args.issue:
        parser.error("Provide --bug, --issue, or both.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Set OPENAI_API_KEY environment variable first.")
    github_token = os.environ.get("GITHUB_TOKEN")
    client = OpenAI(api_key=api_key)

    issue: Issue | None = None
    if args.issue:
        print(f"📥 Fetching issue {args.issue} ...")
        try:
            issue = fetch_issue(args.issue, token=github_token)
        except Exception as exc:
            sys.exit(f"Failed to fetch issue: {exc}")
        print(f"   #{issue.number}: {issue.title}")

    temp_clone: Path | None = None
    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
        if not repo_path.is_dir():
            sys.exit(f"Repo path not found: {repo_path}")
    elif issue is not None:
        print(f"\n📦 Cloning {issue.repo_clone_url} ...")
        try:
            repo_path = clone_to_temp(issue.repo_clone_url)
            temp_clone = repo_path
        except Exception as exc:
            sys.exit(f"Failed to clone repo: {exc}")
        print(f"   Cloned to {repo_path}")
    else:
        sys.exit("Provide either --repo or --issue so I can find the target repo.")

    bug_description = args.bug
    if not bug_description and issue is not None:
        bug_description = issue.as_bug_description()

    try:
        run_fix(client, repo_path, bug_description, args.keep_fix)
    finally:
        if temp_clone is not None and not args.keep_clone:
            print(f"\n🧹 Cleaning up temp clone at {temp_clone}")
            cleanup(temp_clone)
        elif temp_clone is not None:
            print(f"\n   Keeping temp clone at {temp_clone}")


if __name__ == "__main__":
    main()