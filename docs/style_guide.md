# PawControl Style Guide (Home Assistant)

Dieser Style Guide fasst die verbindlichen Entwicklungsrichtlinien der Home Assistant Developer Docs zusammen, die als Quelle der Wahrheit für alle Beiträge am `custom_components/pawcontrol`-Projekt dienen.

## Geltungsbereich

- **Verbindlich für jede Änderung** an der Integration, Dokumentation, Tests und unterstützenden Skripten.
- **Abweichungen sind nicht erlaubt**, außer wenn die Home Assistant Developer Docs selbst explizit Ausnahmen definieren.

## Grundprinzipien

- **Konformität mit Home Assistant**: Architektur, Stil, Übersetzungen, Testing und Review folgen den [offiziellen Vorgaben](https://developers.home-assistant.io/docs/development_guidelines).
- **Klare Trennung von Verantwortlichkeiten**: Komponenten, Plattformen, Config/Options Flows und Services halten sich an die in den [Architektur- und Integrationsdokumenten](https://developers.home-assistant.io/docs/architecture_components) beschriebenen Zuständigkeiten.
- **Qualität vor Geschwindigkeit**: Jeder Beitrag muss den [Entwicklungs-](https://developers.home-assistant.io/docs/development_tips) und [Testempfehlungen](https://developers.home-assistant.io/docs/development_testing) folgen.

## Dateistruktur & Manifest

- **Integration File Structure** strikt einhalten. (https://developers.home-assistant.io/docs/creating_integration_file_structure)
- **Manifest** nach Vorgaben pflegen: Pflichtfelder, Abhängigkeiten, Versionierung und Quality Scale müssen konsistent sein. (https://developers.home-assistant.io/docs/creating_integration_manifest)

## Config Entries & Flows

- Config- und Options-Flows müssen die Vorgaben für Handler, Schema-Validierung und Reauth/Retry-Logik erfüllen. (https://developers.home-assistant.io/docs/config_entries_config_flow_handler, https://developers.home-assistant.io/docs/config_entries_options_flow_handler)
- YAML-Konfiguration ist nur zulässig, wenn sie im offiziellen Leitfaden vorgesehen ist. (https://developers.home-assistant.io/docs/configuration_yaml_index)

## Internationalisierung

- Alle user-facing Strings in `strings.json` und `translations/` pflegen.
- Übersetzungsrichtlinien exakt befolgen; keine hardcodierten Strings. (https://developers.home-assistant.io/docs/internationalization/custom_integration)

## Tests & Qualität

- Tests gemäß Home Assistant Testing Guidelines schreiben und pflegen. (https://developers.home-assistant.io/docs/development_testing)
- Vor einem Release die Home Assistant Development Checklist abarbeiten. (https://developers.home-assistant.io/docs/development_checklist)

## Code Review Standards

- Komponenten-Review-Checkliste anwenden. (https://developers.home-assistant.io/docs/creating_component_code_review)
- Plattform-Review-Checkliste anwenden. (https://developers.home-assistant.io/docs/creating_platform_code_review)

## Laufende Aktualisierung

- Die Home Assistant Developer Docs gelten als lebende Dokumentation. Wenn sich Regeln ändern, muss dieser Style Guide umgehend aktualisiert werden.
- Bei Unsicherheiten gilt immer die jeweils aktuelle Version der Home Assistant Dokumentation: https://developers.home-assistant.io/docs/
