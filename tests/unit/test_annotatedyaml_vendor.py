"""Regression tests for the vendored annotatedyaml entry points."""

from __future__ import annotations

import re

import pytest
from annotatedyaml._vendor import yaml as vendored_yaml


def test_load_accepts_legacy_loader_keyword() -> None:
    data = vendored_yaml.load("answer: 42", Loader=vendored_yaml.FullLoader)
    assert data == {"answer": 42}


def test_safe_load_accepts_legacy_loader_keyword() -> None:
    data = vendored_yaml.safe_load("answer: 42", Loader=vendored_yaml.FullLoader)
    assert data == {"answer": 42}


def test_dump_accepts_legacy_dumper_keyword() -> None:
    payload = {"answer": 42}
    rendered = vendored_yaml.dump(payload, Dumper=vendored_yaml.Dumper)
    assert "answer" in rendered
    assert "42" in rendered


def test_conflicting_loader_alias_raises() -> None:
    message = "load() received both 'Loader' and its replacement"
    with pytest.raises(TypeError, match=re.escape(message)):
        vendored_yaml.load(
            "answer: 42",
            vendored_yaml.FullLoader,
            Loader=vendored_yaml.FullLoader,
        )
