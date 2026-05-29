cat > README.md << 'EOF'
# Bug Fixer

An LLM-driven tool that reads bug reports, proposes patches, validates them
against a test suite, and only keeps fixes that reduce the failing-test set
without introducing regressions.

## V0 — Local CLI

```bash
python -m bug_fixer.fix \
  --repo path/to/target/repo \
  --bug "natural language bug description"
```

Requires:
- Python 3.10+
- `pip install -r requirements.txt`
- `OPENAI_API_KEY` set in environment
- Target repo must have a `src/` directory and a runnable `pytest` suite

## How V0 judges a fix

1. Run the test suite before the patch, record passing/failing sets.
2. Ask the LLM for a patch (plain-text + code fence transport).
3. Reject patches that don't parse as Python (AST pre-flight check).
4. Apply the patch and re-run the suite.
5. Keep the patch only if no previously passing test now fails AND at least
   one previously failing test now passes. Otherwise revert.

## Roadmap

- **V1** — GitHub integration: fetch issues by URL, clone repo, open PRs.
- **V2** — Vector retrieval for relevant files, Docker sandboxing, retry loop.
EOF