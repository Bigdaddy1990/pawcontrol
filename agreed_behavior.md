# Non-Deceptive Git Behavior

## Definition
Non-deceptive Git behavior means interacting with the repository in a
transparent and truthful way. All Git operations and reported results
must accurately reflect the state of the repository without hiding,
misrepresenting, or fabricating information.

## Specification
- Execute Git and development commands exactly as reported. Do not claim
  to have run commands that were not executed.
- Surface command output that is relevant for understanding success or
  failure; do not omit error messages or important warnings.
- Describe repository changes truthfully, including limitations or
  unresolved issues.
- Keep the working tree clean. Stage and commit only the files actually
  modified, and avoid altering or amending existing commits.
- Respect project policies, configuration files, and any directory-level
  instructions such as `AGENTS.md`.

## Acceptance Criteria
- Command logs and file listings accurately match the actions that were
  performed.
- Commit history shows only the intended changes with meaningful commit
  messages.
- No discrepancies exist between reported test or lint results and the
  actual command outputs.
