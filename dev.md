# Development plan

## Aktueller Baustellenüberblick

- Die Test-Suite verlässt sich inzwischen auf umfangreiche Home-Assistant-Stubs,
  doch einzelne Helfer wie `_async_make_resolver` fehlen noch und lassen die
  HACC-Fixtures frühzeitig abstürzen.
- Das pytest-Plugin `tests/plugins/asyncio_stub.py` stellt zwar ein Event-Loop
  bereit, allerdings tauchen nach dem Stub-Import weitere Module auf, die aus
  dem echten `homeassistant` Paket stammen und dadurch neue AttributeError-
  Meldungen verursachen.
- Der Entwicklungsplan muss die verbleibenden Hürden (zeroconf resolver,
  event-loop patches, fehlende Helper) explizit dokumentieren, damit alle
  Platinum-relevanten Checks (Ruff, Pytest, Guard-Skripte) zuverlässig laufen.

## Offene Fehler und Verbesserungen

- `_async_make_resolver` fehlt in `homeassistant.helpers.aiohttp_client` sobald
  die Stubs geladen werden. Dadurch bricht das Fixture
  `mock_zeroconf_resolver` im `pytest_homeassistant_custom_component`-Plugin ab.
- Sobald echte `homeassistant.*` Module bereits importiert wurden, schlägt das
  Stub-Setup fehl. `install_homeassistant_stubs()` muss konsequent alle
  vorhandenen Module bereinigen, bevor die Ersatzmodule registriert werden.
- Nach der Stabilisierung der Stubs müssen `pytest -q`, `ruff check` sowie die
  Guard-Skripte wieder regelmäßig ausgeführt und im CI verankert werden, damit
  neue Regressionsquellen (Entity-Factory, Repairs-Flows, Runtime-Daten) sofort
  sichtbar werden.

### Priorisierte Maßnahmen

1. Die fehlenden Helfer (`_async_make_resolver`, zusätzliche aiohttp/zeroconf-
   Attribute) in den Stubs ergänzen und mit den Plugins von HACC abgleichen.
2. Das Event-Loop-Plugin finalisieren und sicherstellen, dass `pytest -q` ohne
   Race-Conditions durchläuft.
3. Nach jedem größeren Stub-Update `ruff check`, `pytest -q` und die
   Guard-Skripte (`script.enforce_test_requirements`,
   `scripts/enforce_shared_session_guard.py`) ausführen, um Platinum-Standards
   zu belegen.

#### Funktionale Abdeckung

- Sobald pytest wieder stabil läuft, gezielt die Reparatur- und Entity-Factory-
  Tests beobachten, da sie zuerst anschlagen, wenn die Home-Assistant-Shims
  driftig werden.
