"""Tests for pytest_cov plugin session start configuration."""

from types import SimpleNamespace

from pytest_cov import plugin


class _CoverageRecorder:
    """Capture coverage construction arguments."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.started = False

    def start(self) -> None:
        self.started = True


def test_sessionstart_uses_include_without_source(monkeypatch) -> None:
    """Include patterns should disable source roots to avoid conflicts."""
    created: list[_CoverageRecorder] = []

    def _coverage_factory(**kwargs):
        recorder = _CoverageRecorder(**kwargs)
        created.append(recorder)
        return recorder

    monkeypatch.setattr(plugin.coverage, "Coverage", _coverage_factory)

    config = SimpleNamespace(
        option=SimpleNamespace(
            cov=["custom_components/pawcontrol"],
            cov_branch=False,
        )
    )
    session = SimpleNamespace(config=config)

    plugin.pytest_sessionstart(session)

    assert created
    recorder = created[0]
    assert recorder.started is True
    assert recorder.kwargs["include"] is not None
    assert recorder.kwargs["source"] is None


def test_sessionstart_without_cov_sources_keeps_source_none(monkeypatch) -> None:
    """Empty ``--cov`` options should not inject include or source filters."""
    created: list[_CoverageRecorder] = []

    def _coverage_factory(**kwargs):
        recorder = _CoverageRecorder(**kwargs)
        created.append(recorder)
        return recorder

    monkeypatch.setattr(plugin.coverage, "Coverage", _coverage_factory)

    config = SimpleNamespace(option=SimpleNamespace(cov=[], cov_branch=True))
    session = SimpleNamespace(config=config)

    plugin.pytest_sessionstart(session)

    recorder = created[0]
    assert recorder.kwargs["branch"] is True
    assert recorder.kwargs["include"] is None
    assert recorder.kwargs["source"] is None


def test_sessionstart_skips_when_coverage_dependency_missing(monkeypatch) -> None:
    """Session start should no-op when ``coverage`` is unavailable."""
    monkeypatch.setattr(plugin, "coverage", None)

    config = SimpleNamespace(
        option=SimpleNamespace(cov=["custom_components/pawcontrol"])
    )
    session = SimpleNamespace(config=config)

    plugin.pytest_sessionstart(session)

    assert not hasattr(config, "_pawcontrol_cov")


def test_controller_configure_skips_when_coverage_dependency_missing(
    monkeypatch,
) -> None:
    """Controller setup should skip when ``coverage`` cannot be imported."""
    monkeypatch.setattr(plugin, "coverage", None)

    controller = plugin._CoverageController(config=SimpleNamespace())
    controller.pytest_configure(
        SimpleNamespace(
            option=SimpleNamespace(cov_sources=["custom_components/pawcontrol"])
        )
    )

    assert controller._coverage is None
