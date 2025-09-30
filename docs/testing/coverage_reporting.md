# Coverage Reporting Playbook

This guide documents how PawControl maintains the branch-aware coverage gate,
keeps the README badge in sync with the latest results, and provides the
required evidence snippet for every pull request.

## 1. Run the canonical coverage command

```bash
pytest --cov=custom_components.pawcontrol \
       --cov-branch \
       --cov-report=term-missing \
       --cov-report=xml
```

The invocation mirrors the options enforced in `pytest.ini` and produces:

- A terminal summary with statement and branch coverage (minimum 95 %).
- `coverage.xml` for automation or badge generation.
- `htmlcov/` for local inspection when deeper analysis is needed.

> **Tip:** Use `--maxfail=1 --disable-warnings` during local loops for the same
> fast feedback configuration used in CI.

## 2. Update the coverage badge

1. Read the current line coverage percentage from the pytest summary or from
   `coverage.xml` (`line-rate` attribute).
2. Update the badge query string in [`README.md`](../../README.md) so the label
   reflects the freshly generated percentage. For example, a coverage of 99.6 %
   becomes: `https://img.shields.io/badge/Coverage-99.6%25-brightgreen.svg`.
3. Commit the README change alongside the code and tests. The badge links back
   to this playbook for future contributors.

## 3. Documenting PR evidence

Every pull request must include the command output to prove the coverage gate
has been met. Copy the final lines from the pytest run into the PR description
using the following template:

````markdown
```bash
pytest --cov=custom_components.pawcontrol --cov-branch --cov-report=term-missing
```
```
15 passed in 0.25s
Branch coverage: 100%
Line coverage: 100%
```
````

If coverage ever falls below the 95 % threshold, the CI workflow fails and the
PR must add or adjust tests before merging.

## 4. Triage checklist when coverage drops

- [ ] Inspect `coverage.xml` to identify files or branches with misses.
- [ ] Prioritise gaps in the service/resilience layer to keep reliability high.
- [ ] Update or add tests, re-run the canonical command, and refresh the badge.
- [ ] Capture the new output in the PR description.

Following this loop guarantees ≥95 % branch coverage and 100 % PRs with test
proof, matching the quality gates advertised in the documentation portal.
