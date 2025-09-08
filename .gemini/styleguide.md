<!-- .gemini/styleguide.md -->
# Paw Control Style Guide

## Ziel
Konsequente, sichere, wartbare Codebase. Gemini kommentiert kurz, konkret, mit Fix-Vorschlag.

## Review-Regeln für Gemini
- Fokus: Korrektheit, Sicherheit, Wartbarkeit, Effizienz. Keine Nits. Nur Abweichungen mit Impact melden. :contentReference[oaicite:1]{index=1}  
- Ein Issue = ein Kommentar. Struktur: **Problem → Warum → Konkreter Patch**.
- Vorschläge als diffs in kleinstmöglichen Änderungen.
- Priorisierung: Sicherheitsrisiken > Logikfehler > Performance > Style.

## Team-Standards
- Sprache in Code und Docs: Englisch.
- Tests Pflicht für neue Logik. Ziel: sinnvolle Abdeckung, nicht Quote.
- Keine Secrets, keine PII in Logs. Eingaben validieren. Fail fast bei Invarianten.
- Logging: strukturiert, Level sauber setzen. Kein Spam.
- Fehler: spezifische Exceptions. In Go Fehler wrappen. In TS `unknown` behandeln.
- Abhängigkeiten pinnen. Breaking-Changes dokumentieren.

## Python
- PEP 8 Basis mit 100 Zeichen Zeilenlänge.
- Typen überall. `mypy --strict` anstreben.
- Format: Black. Lint: Ruff oder Pylint.
- Async nur wenn nötig. I/O kapseln.
- Pydantic v2 für DTOs, wenn vorhanden.

## TypeScript
- `strict: true`. Keine `any`. Nutzen `unknown` + Narrowing.
- ESLint + Prettier. Ziel ES2022.
- API-Modelle typisieren. Zod oder TypeBox für Runtime-Validierung.
- React: Server Components bevorzugen, falls Next.js. Hooks klein und fokussiert.

## Go
- `gofmt` und `go vet` verbindlich.
- Kontext immer durchreichen. Deadlines setzen.
- Fehler mit `%w` wrappen. Sentinel errors sparsam.
- Concurrency: Race-Detector in CI.

## Security Quick-Checks
- SQL: nur parametrisierte Queries.
- Web: CSRF, XSS, SSRF im Blick. Output-Encoding.
- Krypto: nur geprüfte Libs. Keine Eigenbauten.

## Performance
- Erst messen, dann optimieren. Hot-paths kennzeichnen.
- Allokationen reduzieren. Caches mit TTL und Metriken.

## PR-Erwartungen
- Klein halten. Beschreibung mit Motivation, Risiken, Rollback-Plan.
- Falls Migration: Migrationsschritte und Backfill nennen.

## Stilkleinigkeiten
- Namen klar, keine Abkürzungen. Magic Numbers vermeiden.
- Kommentare erklären das „Warum“. Docstrings für öffentliche APIs.
