# Coverage Gap Report (Branch + Line)

## Snapshot-Metadaten

- **Snapshot-Datum (UTC):** 2026-04-07T02:33:24Z
- **Commit-SHA:** `1ef76b717cf547e6e242bf068c1a6e50e3a982e2`
- **Coverage-Artefakte:** `coverage.xml`, `htmlcov/index.html`

## Reproduzierbarer Run (Repo-Parameter)

Verwendet wurden die im Repository etablierten Coverage-Parameter (`--cov-branch`, XML- und HTML-Report).

```bash
python -m pytest tests/
```

Hinweis zur Reproduzierbarkeit in dieser Umgebung:

- Der Run nutzt die in `pyproject.toml` hinterlegten `addopts`, darunter:
  - `--cov=custom_components/pawcontrol`
  - `--cov-branch`
  - `--cov-report=xml:coverage.xml`
  - `--cov-report=html:htmlcov`
- Der Testlauf endete mit bestehenden Testfehlern, hat aber den Coverage-Snapshot erzeugt.

## Run-Ergebnis (Kurzfassung)

- Ergebnis: `19 failed, 5803 passed, 1 skipped, 3 errors`
- Gesamt-Coverage: `14.28%` (`23259` Statements, `19938` missing)

## Datengrundlage für Folgearbeiten

Die Priorisierung in `docs/coverage_hotspot_backlog.md` basiert **ausschließlich** auf diesem Snapshot (`coverage.xml`) vom oben genannten Datum/Commit.
