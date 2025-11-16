"""Regression tests for the vendored annotatedyaml entry points."""

from __future__ import annotations

import re

import pytest
from annotatedyaml._vendor import yaml as vendored_yaml


class _DummyLoader:
    """Simple loader that records lifecycle interactions for tests."""

    def __init__(self, stream: str, has_data: bool = False) -> None:
        self.stream = stream
        self.disposed = False
        self._has_data = has_data

    def get_single_data(self) -> str:
        return self.stream

    def check_data(self) -> bool:
        return self._has_data

    def get_data(self) -> str:
        if not self._has_data:
            raise RuntimeError("No data available - check_data() returned False")
        return self.stream

    def dispose(self) -> None:
        self.disposed = True


def test_load_accepts_legacy_loader_keyword() -> None:
    data = vendored_yaml.load("answer: 42", Loader=vendored_yaml.FullLoader)
    assert data == {"answer": 42}


def test_load_accepts_positional_loader_argument() -> None:
    data = vendored_yaml.load("answer: 42", vendored_yaml.FullLoader)
    assert data == {"answer": 42}


def test_safe_load_accepts_legacy_loader_keyword() -> None:
    data = vendored_yaml.safe_load("answer: 42", Loader=vendored_yaml.FullLoader)
    assert data == {"answer": 42}


def test_safe_load_accepts_positional_loader_argument() -> None:
    data = vendored_yaml.safe_load("answer: 42", vendored_yaml.FullLoader)
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


def test_extract_legacy_loader_returns_value_and_strips_keyword() -> None:
    kwargs = {"Loader": _DummyLoader}
    result = vendored_yaml._extract_legacy_loader("load", kwargs)
    assert result is _DummyLoader
    assert kwargs == {}


def test_extract_legacy_loader_rejects_other_keywords() -> None:
    kwargs = {"Loader": _DummyLoader, "unexpected": True}
    message = "load() got unexpected keyword argument"
    with pytest.raises(TypeError, match=re.escape(message)):
        vendored_yaml._extract_legacy_loader("load", kwargs)


def test_select_loader_prefers_explicit_loader_cls() -> None:
    selected = vendored_yaml._select_loader(
        "load", loader_cls=_DummyLoader, legacy_loader=None
    )
    assert selected is _DummyLoader


def test_select_loader_prefers_legacy_loader_argument() -> None:
    selected = vendored_yaml._select_loader(
        "load", loader_cls=None, legacy_loader=_DummyLoader
    )
    assert selected is _DummyLoader


def test_select_loader_conflicts_raise_type_error() -> None:
    message = "load() received both 'Loader' and its replacement"
    with pytest.raises(TypeError, match=re.escape(message)):
        vendored_yaml._select_loader(
            "load",
            loader_cls=_DummyLoader,
            legacy_loader=_DummyLoader,
        )


def test_select_loader_missing_required_argument_raises() -> None:
    message = "load() missing 1 required positional argument: 'Loader'"
    with pytest.raises(TypeError, match=re.escape(message)):
        vendored_yaml._select_loader(
            "load", loader_cls=None, legacy_loader=None, required=True
        )


def test_select_loader_uses_default_loader_when_available() -> None:
    selected = vendored_yaml._select_loader(
        "load",
        loader_cls=None,
        legacy_loader=None,
        default_loader=_DummyLoader,
    )
    assert selected is _DummyLoader


def test_load_all_accepts_positional_loader_argument() -> None:
    payload = "---\nanswer: 42\n---\nanswer: 43"
    data = list(vendored_yaml.load_all(payload, vendored_yaml.FullLoader))
    assert data == [{"answer": 42}, {"answer": 43}]


def test_safe_load_all_accepts_positional_loader_argument() -> None:
    payload = "---\nanswer: 42\n---\nanswer: 43"
    data = list(vendored_yaml.safe_load_all(payload, vendored_yaml.SafeLoader))
    assert data == [{"answer": 42}, {"answer": 43}]
