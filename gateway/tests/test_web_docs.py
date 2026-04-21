"""Tests for gateway.web_docs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.web_docs import render_docs


def test_render_docs_returns_russian_html_by_default():
    html = render_docs()
    assert isinstance(html, str)
    assert "onec-mcp-universal" in html


def test_render_docs_returns_english_variant():
    html = render_docs("en")
    assert isinstance(html, str)
    assert "Built-in BSL dependency graph" in html
