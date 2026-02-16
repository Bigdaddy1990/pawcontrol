"""Regression tests for the vendored annotatedyaml entry points."""

import re

import pytest

vendored_yaml = pytest.importorskip(
  "annotatedyaml._vendor.yaml",
  reason="annotatedyaml does not vendor PyYAML in this environment",
)


class _DummyLoader:
  """Simple loader that records lifecycle interactions for tests."""  # noqa: E111

  def __init__(self, stream: str, has_data: bool = False) -> None:  # noqa: E111
    self.stream = stream
    self.disposed = False
    self._has_data = has_data

  def get_single_data(self) -> str:  # noqa: E111
    return self.stream

  def check_data(self) -> bool:  # noqa: E111
    return self._has_data

  def get_data(self) -> str:  # noqa: E111
    if not self._has_data:
      raise RuntimeError("No data available - check_data() returned False")  # noqa: E111
    self._has_data = False
    return self.stream

  def dispose(self) -> None:  # noqa: E111
    self.disposed = True


def test_load_accepts_legacy_loader_keyword() -> None:
  data = vendored_yaml.load("answer: 42", Loader=vendored_yaml.FullLoader)  # noqa: E111
  assert data == {"answer": 42}  # noqa: E111


def test_load_accepts_positional_loader_argument() -> None:
  data = vendored_yaml.load("answer: 42", vendored_yaml.FullLoader)  # noqa: E111
  assert data == {"answer": 42}  # noqa: E111


def test_safe_load_accepts_legacy_loader_keyword() -> None:
  data = vendored_yaml.safe_load("answer: 42", Loader=vendored_yaml.SafeLoader)  # noqa: E111
  assert data == {"answer": 42}  # noqa: E111


def test_safe_load_rejects_unsafe_loader() -> None:
  message = r"safe_load\(\) custom Loader must be a subclass"  # noqa: E111
  with pytest.raises(ValueError, match=message):  # noqa: E111
    vendored_yaml.safe_load("answer: 42", Loader=vendored_yaml.UnsafeLoader)


def test_safe_load_all_rejects_unsafe_loader() -> None:
  message = r"safe_load_all\(\) custom Loader must be a subclass"  # noqa: E111
  with pytest.raises(ValueError, match=message):  # noqa: E111
    list(vendored_yaml.safe_load_all("answer: 42", Loader=vendored_yaml.UnsafeLoader))


def test_dump_accepts_legacy_dumper_keyword() -> None:
  payload = {"answer": 42}  # noqa: E111
  rendered = vendored_yaml.dump(payload, Dumper=vendored_yaml.Dumper)  # noqa: E111
  assert "answer" in rendered  # noqa: E111
  assert "42" in rendered  # noqa: E111


def test_load_without_loader_argument_raises() -> None:
  message = "load() missing 1 required positional argument: 'Loader'"  # noqa: E111
  with pytest.raises(TypeError, match=re.escape(message)):  # noqa: E111
    vendored_yaml.load("answer: 42")


def test_conflicting_loader_alias_raises() -> None:
  message = "load() received both 'Loader' and its replacement"  # noqa: E111
  with pytest.raises(TypeError, match=re.escape(message)):  # noqa: E111
    vendored_yaml.load(
      "answer: 42",
      vendored_yaml.FullLoader,
      Loader=vendored_yaml.FullLoader,
    )


def test_extract_legacy_loader_returns_value_and_strips_keyword() -> None:
  kwargs = {"Loader": _DummyLoader}  # noqa: E111
  result = vendored_yaml._extract_legacy_loader("load", kwargs)  # noqa: E111
  assert result is _DummyLoader  # noqa: E111
  assert kwargs == {}  # noqa: E111


def test_extract_legacy_loader_rejects_other_keywords() -> None:
  kwargs = {"Loader": _DummyLoader, "unexpected": True}  # noqa: E111
  message = "load() got unexpected keyword argument"  # noqa: E111
  with pytest.raises(TypeError, match=re.escape(message)):  # noqa: E111
    vendored_yaml._extract_legacy_loader("load", kwargs)


def test_select_loader_prefers_explicit_loader_cls() -> None:
  selected = vendored_yaml._select_loader(  # noqa: E111
    "load", loader_cls=_DummyLoader, legacy_loader=None
  )
  assert selected is _DummyLoader  # noqa: E111


def test_select_loader_prefers_legacy_loader_argument() -> None:
  selected = vendored_yaml._select_loader(  # noqa: E111
    "load", loader_cls=None, legacy_loader=_DummyLoader
  )
  assert selected is _DummyLoader  # noqa: E111


def test_select_loader_conflicts_raise_type_error() -> None:
  message = "load() received both 'Loader' and its replacement"  # noqa: E111
  with pytest.raises(TypeError, match=re.escape(message)):  # noqa: E111
    vendored_yaml._select_loader(
      "load",
      loader_cls=_DummyLoader,
      legacy_loader=_DummyLoader,
    )


def test_select_loader_missing_required_argument_raises() -> None:
  message = "load() missing 1 required positional argument: 'Loader'"  # noqa: E111
  with pytest.raises(TypeError, match=re.escape(message)):  # noqa: E111
    vendored_yaml._select_loader(
      "load", loader_cls=None, legacy_loader=None, required=True
    )


def test_select_loader_uses_default_loader_when_available() -> None:
  selected = vendored_yaml._select_loader(  # noqa: E111
    "load",
    loader_cls=None,
    legacy_loader=None,
    default_loader=_DummyLoader,
  )
  assert selected is _DummyLoader  # noqa: E111


def test_load_all_accepts_positional_loader_argument() -> None:
  payload = "---\nanswer: 42\n---\nanswer: 43"  # noqa: E111
  data = list(vendored_yaml.load_all(payload, vendored_yaml.FullLoader))  # noqa: E111
  assert data == [{"answer": 42}, {"answer": 43}]  # noqa: E111


def test_safe_load_all_accepts_positional_loader_argument() -> None:
  payload = "---\nanswer: 42\n---\nanswer: 43"  # noqa: E111
  data = list(vendored_yaml.safe_load_all(payload, vendored_yaml.SafeLoader))  # noqa: E111
  assert data == [{"answer": 42}, {"answer": 43}]  # noqa: E111
