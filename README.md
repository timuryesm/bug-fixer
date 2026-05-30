# Bug Fixer

> An LLM-driven tool that reads GitHub issues, proposes patches, validates them against the test suite, and opens pull requests — autonomously.

## What it does

You point it at a GitHub issue describing a bug in a Python project. It fetches the issue, clones the repo, runs the test suite to record the failing tests, asks an LLM for a patch, validates the patch parses as Python before touching disk, applies it, re-runs the suite, and decides whether to keep the fix based on a regression-aware comparison of the test results. If the fix is good, it pushes a new branch and opens a pull request whose description includes the LLM's reasoning and the before/after test counts.

## Demo

Two pull requests autonomously generated against [buggy-calc](https://github.com/timuryesm/buggy-calc), a small intentionally-broken Python library used as a test target:

- [PR #2 — Fix #1: `is_prime(1)` returns `True`](https://github.com/timuryesm/buggy-calc/pull/2)
- [PR #4 — Fix #3: `fibonacci` off by one](https://github.com/timuryesm/buggy-calc/pull/4)

Each was opened by a single command:

```bash
python -m bug_fixer.fix --issue <github-issue-url> --open-pr
```

## How it works

The pipeline is seven stages, each independently testable:

1. **Fetch issue** — GitHub REST API call, parse title and body into a typed `Issue` record.
2. **Clone target** — shallow `git clone` over HTTPS into a temp directory.
3. **Baseline tests** — run `pytest -v`, parse output into passing/failing sets of test IDs.
4. **Ask LLM** — single OpenAI call (`gpt-4o-mini`, `temperature=0`) with the issue body and the full source of the repo's `src/` directory.
5. **Pre-flight validate** — parse the proposed patch with `ast.parse()` before any disk write. Reject syntactically invalid code without touching the file.
6. **Apply + retest** — back up the original, write the patch, re-run `pytest`.
7. **Judge** — compare pre/post test sets. Four outcomes are distinguished: *catastrophic* (tests didn't run after patch), *regression* (previously-passing test now fails), *no-op* (no failing test newly passes), or *progress* (regression-free and at least one newly-passing test). Only *progress* keeps the patch; everything else reverts.

On *progress*, the tool creates a new branch, commits the change under a dedicated `bug-fixer` author identity, pushes via the GitHub token, and opens a PR linked back to the issue with `Fixes #N`.

## Engineering decisions worth noting

**LLM output transport.** I initially used JSON mode with the patched file as a JSON string field. This broke on files with triple-quoted docstrings: the model lost track of escape sequences in long string outputs and dropped quote characters, producing files that wouldn't parse. Switched to a plain-text format with a markdown code fence for the file body. The escape-sequence problem disappeared because the model writes raw Python inside the fence.

**Delta-aware test judging.** The naive criterion "all tests pass after patch" rejects good fixes in any codebase with multiple bugs. The opposite criterion "fewer failures than before" silently accepts catastrophic patches that cause pytest to error out during test collection. The implementation distinguishes both cases by comparing the *sets of test IDs* that ran before and after, not just the counts.

**AST pre-flight check.** Validating that the patch parses as Python before applying it eliminates an entire class of "broken patch overwrites real file" failures. Three lines of code; large fraction of the actual robustness gain.

**Author identity via env vars, not git config.** The bot's commit author identity is set per-commit through `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` rather than `git config user.name`. The cloned repo's config is never modified, so the tool can't accidentally leak its identity into commits made by humans working in the same directory.

**Token isolation.** GitHub tokens are scoped to a single repository with the minimum required permissions (Issues read, Pull Requests write, Contents write), and are never written into the cloned repo's git config. The token appears in a push URL passed to `subprocess` and is scrubbed from any error output before it can be logged.

## What this project taught me

Generating an AI patch is the easy part. The hard parts are validating the patch, deciding when to trust it, and surviving the systematic ways the model fails.

Every layer of the pipeline above the LLM call was driven by a real failure I watched happen during development: a docstring serialization error, a JSON escape bug, a "successful" patch that actually broke the test runner. The validation layer is where the engineering lives.

The other thing I learned is that "the model can't solve this task" and "the model can solve this task but my plumbing is broken" look identical from the outside, and confusing them costs hours. The way you tell them apart is by logging the model's reasoning trace and asking whether it was correct, then deciding which layer of the system to fix.

## Limitations / V2 roadmap

V1 makes several assumptions that work for small repos and break for large ones:

- Target repo must have a `src/` directory and a runnable `pytest` suite. Real codebases vary far more.
- Entire `src/` contents are sent to the LLM in every call. Doesn't scale beyond a few thousand lines.
- Tests run on the host machine. A malicious target repo could execute arbitrary code via its test suite. Production use would require Docker sandboxing.
- One LLM call per fix, no retry on transient failures.
- Single-file patches only. Multi-file bugs would require redesigning the prompt and apply step.

V2 will address these in roughly that order: Docker sandboxing first (safety), then vector-based file retrieval (scale), then retry loops and multi-file support (capability).

## Run it yourself

Requirements: Python 3.10+, an OpenAI API key, and optionally a GitHub fine-grained personal access token (required only for `--open-pr`).

```bash
git clone https://github.com/timuryesm/bug-fixer
cd bug-fixer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY="sk-..."
export GITHUB_TOKEN="github_pat_..."     # only needed for --open-pr

# Fix a bug from a GitHub issue, open a PR with the result:
python -m bug_fixer.fix --issue <issue_url> --open-pr

# Or run locally without GitHub:
python -m bug_fixer.fix --repo path/to/repo --bug "natural language bug description"
```

For the full set of flags:

```bash
python -m bug_fixer.fix --help
```

## Stack

Python 3.10+, OpenAI API (`gpt-4o-mini`), GitHub REST API, `pytest`, `requests`, `ast`.