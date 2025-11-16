# `pyproject.toml` reference for PawControl

The [Python Developer Tooling Handbook](https://pydevtools.com/handbook/reference/pyproject/)
provides an excellent overview of what modern `pyproject.toml` files should
include. This document maps those recommendations to PawControl so maintainers
can quickly verify that our build metadata, tooling configuration, and Home
Assistant workflows stay aligned.

## 1. Core sections

| Section | Purpose | PawControl specifics |
| --- | --- | --- |
| `[build-system]` | Declares the backend and bootstrap requirements described in PEP 517/518. | Uses `setuptools.build_meta` with a minimal `setuptools`/`wheel` bootstrap to keep the integration editable via `pip install -e .`. 【F:pyproject.toml†L2-L8】 |
| `[project]` | Centralises metadata defined by PEP 621, including version policy and runtime dependencies. | Defines the name, description, README, MIT license file, author attribution, keywords, classifiers, Python `>=3.13` gate, runtime dependencies, and external URLs so packaging tools expose the same data as our README. 【F:pyproject.toml†L78-L122】 |
| `[project.optional-dependencies]` | Groups feature- or workflow-specific dependencies. | The `tests` extra mirrors `requirements_test.txt`, enabling `pip install .[tests]` for full CI parity. 【F:pyproject.toml†L124-L141】 |
| Tool sections | Allow linters, test runners, and coverage tooling to share configuration. | Ruff, Pytest, Coverage, and MyPy all read from `pyproject.toml`, ensuring the single-source-of-truth behaviour highlighted in the handbook. 【F:pyproject.toml†L10-L76】 |

## 2. Field highlights

- **Project metadata** – The handbook emphasises keeping descriptions, licenses,
  and classifiers close to the code. PawControl now exposes its MIT license,
  Platinum-grade Home Assistant scope, typed guarantees, and automation
  keywords directly through `[project]`. 【F:pyproject.toml†L78-L110】
- **Runtime dependencies** – Aligns with `requirements.txt` so editable installs
  and extras stay consistent across dev containers and CI. 【F:pyproject.toml†L112-L122】【F:requirements.txt†L1-L4】
- **Test extras** – Mirrors the pinned test stack, including
  `pytest-homeassistant-custom-component`, so the entire Platinum gate can be
  reproduced with a single extras install. 【F:pyproject.toml†L124-L141】【F:requirements_test.txt†L1-L13】
- **Project URLs** – Link back to the repository, docs, and issue tracker,
  making it easier for packaging indexes to direct users to the correct support
  channels. 【F:pyproject.toml†L143-L146】
- **Dynamic version** – The core package delegates version stamping to
  `setuptools_scm`, so the canonical release automation in
  `.github/workflows/release.yml` can inject the same version number into
  Home Assistant manifests and documentation bundles. 【F:pyproject.toml†L101-L110】【F:.github/workflows/release.yml†L1-L120】

## 3. Tool configuration crosswalk

The handbook calls out `pyproject.toml` as the single source of truth for modern
tooling. PawControl keeps all required quality gates here so new contributors
can bootstrap their IDEs without chasing hidden configuration files.

| Handbook focus | PawControl implementation |
| --- | --- |
| **Build backend (PEP 517/518)** | `[build-system]` pins `setuptools.build_meta` so editable installs work everywhere and mirrors the bootstrap requirements the handbook highlights. 【F:pyproject.toml†L1-L8】 |
| **Pytest defaults** | `[tool.pytest.ini_options]` enables strict markers, Warnings-as-errors, coverage reports, and async detection, matching the "single source" goal for tests. 【F:pyproject.toml†L7-L23】 |
| **Ruff (format + lint)** | `[tool.ruff]`/`[tool.ruff.lint.*]` capture the Platinum lint profile, docstring rules, and vendor ignores so engineers never have to juggle `.ruff.toml` files. 【F:pyproject.toml†L25-L62】 |
| **Coverage reports** | `[tool.coverage.*]` configure HTML/XML targets that CI publishes alongside the branch coverage demanded by the handbook. 【F:pyproject.toml†L52-L74】 |
| **MyPy strictness** | `[tool.mypy]` enforces typed defs, no implicit optionals, and explicit package bases, ensuring static analysis stays reproducible from the same file. 【F:pyproject.toml†L64-L74】 |

## 4. Handbook-aligned workflows

1. Treat `pyproject.toml` as the canonical source for build metadata. Whenever a
   README, manifest, or diagnostic makes Platinum claims, confirm the same
   classifiers and URLs exist under `[project]`. 【F:pyproject.toml†L78-L146】
2. Keep `requirements*.txt` and `[project]*` dependencies in lock-step. The
   extras entry exists solely to help contributors run the handbook-mandated
   quality gates (`ruff`, `pytest`, `mypy`, `hassfest`) with one install. 【F:pyproject.toml†L112-L141】【F:requirements_test.txt†L1-L13】
3. When adding new tooling (for example `script.sync_contributor_guides` or a
   JSON schema linter), prefer a `[tool.*]` table here instead of bespoke config
   files so future audits can diff a single document.

## 5. Maintainer checklist

1. When adding or upgrading runtime dependencies, update both
   `requirements.txt` and `[project].dependencies`.
2. When the test stack changes, mirror it in `requirements_test.txt` and the
   `tests` optional dependency so editable installs and `pip install .[tests]`
   stay in sync.
3. Keep the classifiers aligned with Home Assistant’s supported Python version
   and licensing evidence. Bump the `Programming Language :: Python` entries as
   the integration advances.
4. Re-run `ruff format`, `ruff check`, `pytest -q`, `mypy`,
   `python -m script.enforce_test_requirements`, and
   `python -m script.hassfest --integration-path custom_components/pawcontrol`
   after any tooling change so CI sees the same configuration locally.

Maintainers can treat this page as the living bridge between the general
handbook guidance and our specific Home Assistant integration.
