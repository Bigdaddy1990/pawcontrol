# Paw Control – Integration Quality Scale Checklist

This document maps our implementation to the **Integration Quality Scale**.

## Silver (runtime robustness)

- [x] Services registered in `async_setup` and validated via `ServiceValidationError`.
- [x] `PARALLEL_UPDATES` explicitly set for read-only platforms.
- [x] Graceful error handling; entities set `available` accordingly (coordinator-based).
- [x] `async_setup_entry` / `async_unload_entry` implemented; `async_remove_entry` cleans up.
- [x] `strings.json` + translations for errors and services.
- [x] Tests skeleton in place; target coverage ≥ 95% (to be completed in CI).

## Gold (user experience & supportability)

- [x] Diagnostics (`diagnostics.py`) with **redaction** of sensitive data.
- [x] Repair issues & Repair flows (`repairs.py`) for user-guided fixes.
- [x] Device Registry: each dog/tracker is a Device; `unique_id` for entities.
- [x] Entity naming: `_attr_has_entity_name=True`, `translation_key` set; `strings.json` updated.
- [x] Icon translations via `icons.json` with state mappings.
- [x] Reconfigure flow (`async_step_reconfigure`) to change options post-setup.
- [x] Services/Translations in sync; `services.yaml` matches registrations.
- [ ] Brands assets prepared (SVG placeholders here) – PR to `home-assistant/brands` pending.
- [ ] Test coverage ≥ 95% (implement & measure in CI with pytest + coverage).

## Notes

- Discovery not applicable (no discoverable transport). Documented as exception.
- Reauth only needed if authentication is introduced later.

- [x] **GitHub Topics** gesetzt (z. B. `home-assistant`, `hacs`, `integration`) – verbessert Auffindbarkeit im HACS-Store.
