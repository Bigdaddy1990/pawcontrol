.github/copilot-instructions.md

This repository uses `.github/copilot-instructions.md` as the canonical
contributor and bot policy guide. The following agent-specific mirrors must stay
in sync with it, including requirements for ChatGPT, Gemini, Claude, and other
automated tools:

- .claude/agents/copilot-instructions.md
- .gemini/styleguide.md

After updating the canonical guide, run:

```bash
python -m scripts.sync_contributor_guides
```
