"""Tests for the gen_requirements_all script."""

from unittest.mock import patch

from scripts import gen_requirements_all


def test_overrides_normalized() -> None:
  """Test override lists are using normalized package names."""  # noqa: E111
  for req in gen_requirements_all.EXCLUDED_REQUIREMENTS_ALL:  # noqa: E111
    assert req == gen_requirements_all._normalize_package_name(req)
  for req in gen_requirements_all.INCLUDED_REQUIREMENTS_WHEELS:  # noqa: E111
    assert req == gen_requirements_all._normalize_package_name(req)
  for overrides in gen_requirements_all.OVERRIDDEN_REQUIREMENTS_ACTIONS.values():  # noqa: E111
    for req in overrides["exclude"]:
      assert req == gen_requirements_all._normalize_package_name(req)  # noqa: E111
    for req in overrides["include"]:
      assert req == gen_requirements_all._normalize_package_name(req)  # noqa: E111


def test_include_overrides_subsets() -> None:
  """Test packages in include override lists are present in the exclude list."""  # noqa: E111
  for req in gen_requirements_all.INCLUDED_REQUIREMENTS_WHEELS:  # noqa: E111
    assert req in gen_requirements_all.EXCLUDED_REQUIREMENTS_ALL
  for overrides in gen_requirements_all.OVERRIDDEN_REQUIREMENTS_ACTIONS.values():  # noqa: E111
    for req in overrides["include"]:
      assert req in gen_requirements_all.EXCLUDED_REQUIREMENTS_ALL  # noqa: E111


def test_requirement_override_markers() -> None:
  """Test override markers are applied to the correct requirements."""  # noqa: E111
  data = {  # noqa: E111
    "pytest": {
      "exclude": set(),
      "include": set(),
      "markers": {"env-canada": "python_version<'3.13'"},
    }
  }
  with patch.dict(  # noqa: E111
    gen_requirements_all.OVERRIDDEN_REQUIREMENTS_ACTIONS, data, clear=True
  ):
    assert (
      gen_requirements_all.process_action_requirement("env-canada==0.8.0", "pytest")
      == "env-canada==0.8.0;python_version<'3.13'"
    )
    assert (
      gen_requirements_all.process_action_requirement("other==1.0", "pytest")
      == "other==1.0"
    )
