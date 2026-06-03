"""Unit tests for the deterministic layers of bug_fixer.

These tests cover the pure functions — parsers, validators, the AST chunker —
that don't require network access or the OpenAI API. They're what CI runs.
"""

import pytest

from bug_fixer.fix import (
    is_valid_python,
    parse_test_results,
    parse_llm_response,
)
from bug_fixer.github_client import parse_issue_url
from bug_fixer.retrieval import chunk_python_file


# ---- parse_test_results ----

def test_parse_test_results_basic():
    output = (
        "tests/test_math.py::test_one PASSED\n"
        "tests/test_math.py::test_two FAILED\n"
        "tests/test_math.py::test_three PASSED\n"
    )
    passing, failing = parse_test_results(output)
    assert passing == {
        "tests/test_math.py::test_one",
        "tests/test_math.py::test_three",
    }
    assert failing == {"tests/test_math.py::test_two"}


def test_parse_test_results_treats_error_as_failure():
    passing, failing = parse_test_results("tests/test_x.py::test_x ERROR")
    assert failing == {"tests/test_x.py::test_x"}


def test_parse_test_results_ignores_summary_lines():
    output = (
        "tests/test_a.py::test_one PASSED\n"
        "FAILED tests/test_a.py::test_two - assert 1 == 2\n"
    )
    passing, failing = parse_test_results(output)
    assert passing == {"tests/test_a.py::test_one"}
    assert failing == set()


# ---- is_valid_python ----

def test_is_valid_python_accepts_valid_code():
    ok, err = is_valid_python("def foo():\n    return 1\n")
    assert ok is True
    assert err == ""


def test_is_valid_python_rejects_syntax_error():
    ok, err = is_valid_python('"""unterminated docstring')
    assert ok is False
    assert "line" in err.lower()


# ---- parse_llm_response ----

def test_parse_llm_response_well_formed():
    text = (
        "REASONING: The bug is in foo.\n"
        "FILE: src/foo.py\n"
        "```python\n"
        "def foo():\n"
        "    return 1\n"
        "```\n"
    )
    result = parse_llm_response(text)
    assert result["file_path"] == "src/foo.py"
    assert "def foo()" in result["new_content"]
    assert "bug is in foo" in result["reasoning"]


def test_parse_llm_response_no_file_marker_raises():
    with pytest.raises(ValueError, match="FILE:"):
        parse_llm_response("REASONING: did something\n```python\nx = 1\n```")


def test_parse_llm_response_no_code_fence_raises():
    with pytest.raises(ValueError, match="code fence"):
        parse_llm_response("REASONING: x\nFILE: src/foo.py\nbare text\n")


# ---- parse_issue_url ----

def test_parse_issue_url_basic():
    owner, repo, number = parse_issue_url("https://github.com/foo/bar/issues/42")
    assert (owner, repo, number) == ("foo", "bar", 42)


def test_parse_issue_url_trailing_slash():
    _, _, number = parse_issue_url("https://github.com/foo/bar/issues/42/")
    assert number == 42


def test_parse_issue_url_rejects_non_issue_url():
    with pytest.raises(ValueError):
        parse_issue_url("https://github.com/foo/bar/pulls/42")


# ---- chunk_python_file ----

def test_chunk_python_file_finds_top_level_functions():
    source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    chunks = chunk_python_file("src/x.py", source)
    names = [c.name for c in chunks]
    assert "foo" in names
    assert "bar" in names


def test_chunk_python_file_finds_methods_qualified():
    source = "class A:\n    def m(self):\n        pass\n"
    chunks = chunk_python_file("src/x.py", source)
    names = [c.name for c in chunks]
    assert "A" in names
    assert "A.m" in names


def test_chunk_python_file_falls_back_on_syntax_error():
    chunks = chunk_python_file("src/x.py", "def foo(:\n    pass")
    assert len(chunks) == 1
    assert chunks[0].kind == "file"