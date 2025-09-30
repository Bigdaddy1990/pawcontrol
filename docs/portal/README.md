# PawControl Documentation Portal

The documentation portal provides a curated entry point for the project. It
connects the architecture deliverables, quality gates, and operational playbooks
required for the *Architektur & Fehlerkultur* initiative.

## Navigation

| Track | Purpose | Key Resources |
| --- | --- | --- |
| Architecture & Error Culture | Understand the manager layer, error catalogue, and ADR history that enforce maintainability. | [Manager Structure](../architecture/manager_structure.md), [Error Catalog](../architecture/error_catalog.md), [ADR Index](../architecture/adr/) |
| Testing & Quality | Apply the test pyramid, coverage gates, and PR evidence requirements. | [Test Pyramid](../testing/test_pyramid.md), [pytest configuration](../../pytest.ini), [Repository README](../../README.md#-quality--testing) |
| Operations & Observability | Monitor runtime health, resilience metrics, and repair workflows. | [Resilience README](../resilience-README.md), [Diagnostics guide](../diagnostik.md), [System Health module](../../custom_components/pawcontrol/system_health.py) |

## Usage Guidelines

1. **Start with the portal** when onboarding contributors or preparing a PR.
2. **Link test evidence** in every PR description; the quality gate is enforced by
   `pytest --cov-branch --cov-fail-under=95`.
3. **Cross-reference the error catalogue** when raising new exceptions to keep
   diagnostics consistent and actionable.

The portal is intentionally lightweight so teams can embed it in internal wikis
without duplicating content. Each document it references is version-controlled to
keep architectural decisions, error culture, and testing discipline aligned.
