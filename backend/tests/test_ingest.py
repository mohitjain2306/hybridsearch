# backend/tests/test_ingest.py

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.ingest import (
    _make_doc_id,
    _clean_text,
    _make_snippet,
    load_txt_docs,
    run_ingest,
)


# ---------------------------------------------------------------------------
# _make_doc_id
# ---------------------------------------------------------------------------

def test_make_doc_id_format():
    doc_id = _make_doc_id(1, "Space Shuttle")
    parts = doc_id.split("_")
    assert parts[0] == "doc"
    assert len(parts[1]) == 4
    assert parts[1] == "0001"
    assert len(parts[2]) == 8


def test_make_doc_id_zero_padded():
    assert _make_doc_id(42, "Test").startswith("doc_0042_")


def test_make_doc_id_is_deterministic():
    assert _make_doc_id(1, "Space") == _make_doc_id(1, "Space")


def test_make_doc_id_differs_for_different_titles():
    assert _make_doc_id(1, "Space") != _make_doc_id(1, "Medicine")


# ---------------------------------------------------------------------------
# _clean_text
# ---------------------------------------------------------------------------

def test_clean_text_strips_extra_whitespace():
    result = _clean_text("hello   world\n\ntest")
    assert "  " not in result
    assert result == result.strip()


def test_clean_text_removes_citation_markers():
    result = _clean_text("Some text[1] with citations[23]")
    assert "[1]" not in result
    assert "[23]" not in result


def test_clean_text_truncates_at_max_chars():
    long_text = "a" * 5000
    result = _clean_text(long_text)
    assert len(result) <= 3000


def test_clean_text_empty_string():
    assert _clean_text("") == ""


def test_clean_text_returns_string():
    assert isinstance(_clean_text("hello world"), str)


# ---------------------------------------------------------------------------
# _make_snippet
# ---------------------------------------------------------------------------

def test_make_snippet_shorter_than_limit():
    text = "short text"
    assert _make_snippet(text, length=200) == text


def test_make_snippet_truncates_long_text():
    text = "word " * 100
    result = _make_snippet(text, length=50)
    assert len(result) <= 55


def test_make_snippet_adds_ellipsis_when_truncated():
    text = "word " * 100
    result = _make_snippet(text, length=50)
    assert result.endswith("…")


def test_make_snippet_empty_string():
    assert _make_snippet("", length=200) == ""


# ---------------------------------------------------------------------------
# load_txt_docs
# ---------------------------------------------------------------------------

def test_load_txt_docs_reads_txt_files(tmp_path):
    (tmp_path / "test_doc.txt").write_text(
        "This is a test document about space exploration.", encoding="utf-8"
    )
    docs = load_txt_docs(tmp_path, start_index=1)
    assert len(docs) == 1
    assert docs[0]["title"] == "Test Doc"
    assert "space" in docs[0]["text"].lower()


def test_load_txt_docs_empty_dir_returns_empty(tmp_path):
    docs = load_txt_docs(tmp_path, start_index=1)
    assert docs == []


def test_load_txt_docs_doc_id_format(tmp_path):
    (tmp_path / "my_file.txt").write_text("Some content here.", encoding="utf-8")
    docs = load_txt_docs(tmp_path, start_index=5)
    assert docs[0]["doc_id"].startswith("doc_0005_")


def test_load_txt_docs_sets_category_general(tmp_path):
    (tmp_path / "notes.txt").write_text("Random notes about nothing.", encoding="utf-8")
    docs = load_txt_docs(tmp_path, start_index=1)
    assert docs[0]["category"] == "general"


def test_load_txt_docs_has_required_fields(tmp_path):
    (tmp_path / "doc.txt").write_text("Some text content.", encoding="utf-8")
    docs = load_txt_docs(tmp_path, start_index=1)
    doc = docs[0]
    assert "doc_id" in doc
    assert "title" in doc
    assert "text" in doc
    assert "category" in doc
    assert "created_at" in doc


# ---------------------------------------------------------------------------
# run_ingest — output file
# ---------------------------------------------------------------------------

def test_run_ingest_creates_jsonl_file(tmp_path):
    input_dir  = tmp_path / "raw"
    output_dir = tmp_path / "processed"
    input_dir.mkdir()
    (input_dir / "sample.txt").write_text(
        "The space shuttle was a reusable spacecraft operated by NASA.", encoding="utf-8"
    )

    with patch("app.ingest.fetch_wikipedia_docs", return_value=[]):
        count = run_ingest(input_dir, output_dir)

    output_file = output_dir / "docs.jsonl"
    assert output_file.exists()
    assert count >= 1


def test_run_ingest_output_is_valid_jsonl(tmp_path):
    input_dir  = tmp_path / "raw"
    output_dir = tmp_path / "processed"
    input_dir.mkdir()
    (input_dir / "sample.txt").write_text(
        "Antibiotics are used to treat bacterial infections.", encoding="utf-8"
    )

    with patch("app.ingest.fetch_wikipedia_docs", return_value=[]):
        run_ingest(input_dir, output_dir)

    lines = (output_dir / "docs.jsonl").read_text().strip().splitlines()
    for line in lines:
        doc = json.loads(line)
        assert "doc_id" in doc
        assert "title" in doc
        assert "text" in doc
