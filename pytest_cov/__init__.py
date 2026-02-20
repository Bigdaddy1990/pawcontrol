"""Local pytest-cov shim package."""

from .plugin import _CoverageController, pytest_addoption, pytest_configure

__all__ = ["_CoverageController", "pytest_addoption", "pytest_configure"]
