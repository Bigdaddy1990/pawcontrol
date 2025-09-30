# ADR 001: Einführung des Dog Domain Orchestrator

- **Status:** Accepted
- **Datum:** 2025-03-10
- **Betroffene Komponenten:** `custom_components.pawcontrol.coordinator`, `custom_components.pawcontrol.domain`

## Kontext

Der Koordinator der Paw-Control-Integration vereinte bislang sowohl Querschnittsaufgaben (Update-Takt, Resilienz) als auch die konkrete Modulaggregation für jeden Hund. Diese Mischung führte zu über 500 Zeilen Code und erschwerte es, Verantwortlichkeiten klar zuzuordnen oder neue Domänenmodule (z. B. Garten, Gesundheit) konsistent anzubinden.

## Entscheidung

Wir extrahieren mit dem `DogDomainOrchestrator` eine eigenständige Architekturschicht. Der Orchestrator erhält die bestehenden `CoordinatorModuleAdapters` und ist ausschließlich für die Erstellung von "Dog Snapshots" verantwortlich:

- Normalisierung der Modul-Rückgaben und Fehlerzustände
- Vereinheitlichte Erzeugung eines Laufzeit-Snapshots (`DomainSnapshot`)
- Bereitstellung eines leeren Snapshots als Fallback für Fehlerszenarien

Der Koordinator delegiert damit die Domänenlogik und konzentriert sich auf Lebenszyklus- und Resilienzaufgaben.

## Konsequenzen

- **Positive:**
  - Verantwortlichkeiten sind getrennt, wodurch der Koordinator schlanker und wartbarer wird.
  - Neue Domänenmodule können über den Orchestrator angebunden werden, ohne den Koordinator weiter aufzublähen.
  - Fehlerbehandlung je Modul ist zentralisiert und nachvollziehbar dokumentiert.
- **Negative:**
  - Zusätzliche Datei bzw. Modulschicht erhöht die Anzahl der Komponenten.
  - Weitere ADRs sind notwendig, um Folgeentscheidungen (z. B. API-TypedDicts) festzuhalten.

## Nächste Schritte

- Erweiterung des Orchestrators um typisierte Datenmodelle für Module (TypedDicts/Pydantic). ✅ Mit `ModuleSnapshot`/`DomainSnapshot` umgesetzt.
- Anpassung der Config-/Options-Flows, damit Domänenprofile direkt in Snapshots reflektiert werden.
- Ergänzung weiterer ADRs für Config-Flow-Modularisierung und API-Design.
