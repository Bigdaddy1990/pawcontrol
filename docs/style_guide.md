# PawControl Style Guide (Home Assistant)

Dieser Style Guide fasst die verbindlichen Entwicklungsrichtlinien der Home Assistant Developer Docs zusammen, die als Quelle der Wahrheit für alle Beiträge am `custom_components/pawcontrol`-Projekt dienen.

## Geltungsbereich

- **Verbindlich für jede Änderung** an der Integration, Dokumentation, Tests und unterstützenden Skripten.
- **Abweichungen sind nicht erlaubt**, außer wenn die Home Assistant Developer Docs selbst explizit Ausnahmen definieren.

## Grundprinzipien

- **Konformität mit Home Assistant**: Architektur, Stil, Übersetzungen, Testing und Review folgen den [offiziellen Vorgaben](https://developers.home-assistant.io/docs/development_guidelines).
- **Klare Trennung von Verantwortlichkeiten**: Komponenten, Plattformen, Config/Options Flows und Services halten sich an die in den [Architektur- und Integrationsdokumenten](https://developers.home-assistant.io/docs/architecture_components) beschriebenen Zuständigkeiten.
- **Qualität vor Geschwindigkeit**: Jeder Beitrag muss den [Entwicklungs-](https://developers.home-assistant.io/docs/development_tips) und [Testempfehlungen](https://developers.home-assistant.io/docs/development_testing) folgen.
- **Aktualität der Regeln**: Relevante Updates aus dem [Home Assistant Developer Blog](https://developers.home-assistant.io/blog) gelten sofort und sind in Style Guide, Bot-Regeln und Review-Checklisten zu spiegeln.

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
- Quality-Scale Regeln, Action-Setup und Common-Modules beachten und mit der Checkliste abgleichen. (https://developers.home-assistant.io/docs/core/integration-quality-scale/rules, https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-setup/, https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/common-modules, https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist)
- Entwicklungs-Validierung, Typisierung und `check_config` als verbindliche Prüfungen behandeln. (https://developers.home-assistant.io/docs/development_validation, https://developers.home-assistant.io/docs/development_typing, https://www.home-assistant.io/docs/tools/check_config/)

## Code Review Standards

- Komponenten-Review-Checkliste anwenden. (https://developers.home-assistant.io/docs/creating_component_code_review)
- Plattform-Review-Checkliste anwenden. (https://developers.home-assistant.io/docs/creating_platform_code_review)

## Dokumentation, YAML & Examples

- YAML-Dokumentation folgt dem Home Assistant YAML Style Guide. (https://developers.home-assistant.io/docs/documenting/yaml-style-guide)
- Neue Dokumentationsseiten und Beispiele orientieren sich an den offiziellen Templates. (https://developers.home-assistant.io/docs/documenting/create-page, https://developers.home-assistant.io/docs/documenting/integration-docs-examples)

## Plattformverhalten & Automationen

- Signifikante Änderungen, `reproduce_state` und Reparaturen müssen die Core-Plattformregeln erfüllen. (https://developers.home-assistant.io/docs/core/platform/significant_change, https://developers.home-assistant.io/docs/core/platform/reproduce_state, https://developers.home-assistant.io/docs/core/platform/repairs)
- Device Automations und Automations-APIs richten sich nach den offiziellen Spezifikationen. (https://developers.home-assistant.io/docs/device_automation_index, https://developers.home-assistant.io/docs/device_automation_trigger, https://developers.home-assistant.io/docs/device_automation_condition, https://developers.home-assistant.io/docs/device_automation_action, https://developers.home-assistant.io/docs/automations)
- Config Entries und Data Entry Flows folgen den Core-Leitfäden. (https://developers.home-assistant.io/docs/config_entries_index, https://developers.home-assistant.io/docs/data_entry_flow_index)
- Instanz-URL, Reparatur- und LLM/Intent-Integrationen folgen den Home Assistant Richtlinien. (https://developers.home-assistant.io/docs/instance_url, https://developers.home-assistant.io/docs/intent_conversation_api, https://developers.home-assistant.io/docs/intent_builtin, https://developers.home-assistant.io/docs/core/llm/)

## Mobile App Integration

- Native App Integration (Setup, Daten, Sensoren, Benachrichtigungen) ist strikt nach den offiziellen APIs umzusetzen. (https://developers.home-assistant.io/docs/api/native-app-integration/setup, https://developers.home-assistant.io/docs/api/native-app-integration/sending-data, https://developers.home-assistant.io/docs/api/native-app-integration/sensors, https://developers.home-assistant.io/docs/api/native-app-integration/notifications)

## Internationalisierung

- Internationale Unterstützung folgt den HA-Richtlinien für Custom Integrations. (https://developers.home-assistant.io/docs/internationalization/custom_integration)

## Laufende Aktualisierung

- Die Home Assistant Developer Docs gelten als lebende Dokumentation. Wenn sich Regeln ändern, muss dieser Style Guide umgehend aktualisiert werden.
- Bei Unsicherheiten gilt immer die jeweils aktuelle Version der Home Assistant Dokumentation: https://developers.home-assistant.io/docs/
