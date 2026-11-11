> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Die hier genannten lokalen Notes-/Appfenster und festen Appzahlen sind überholt. App-Sichtbarkeit und Serverzugang werden heute aus der aktuellen Gerätefreigabe abgeleitet. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# Lumen app cohesion

Native Qt surfaces, using the existing shared themes and German/English translations.

| Capability | Interface | Acceptance |
| --- | --- | --- |
| App overview | Main Lumen Apps page, desktop launcher, companion-app header | All 12 apps can be found and launched without a terminal; launch failures are visible. Existing navigation indices remain stable. |
| Settings | Shared dialog with named app pages | Each app is represented; companion startup preferences are effective and conflict-checked. Shared appearance, speech and integrations remain single sources of truth. Record-specific account/backup options stay in their app. |
| Knowledge | Main-page gateway to notebook and memory | Opens the requested area in the existing Wissen window; pending saves are preserved. Document indexing remains accessible. No changes to sharing or learning consent. |

Existing notes, jobs, app libraries and user settings are preserved. Validate with isolated Qt tests, DE/EN screenshots and runtime activation before installing locally.

## Delivered

- `lumen-apps` opens page 9; pages 0–8 and existing D-Bus routes are unchanged.
- Files exposes the overview in its menu; companion windows expose Apps and their named settings page in the header.
- Settings includes all 12 apps and a section filter. Per-companion window/last-entry preferences use the shared conflict-checked settings writer. Per-record options are linked to their owning app rather than copied.
- Main Knowledge opens the existing Wissen user/memory areas. Sources remain locally indexed; legacy result captures continue through the existing notebook migration. Sharing and learning flags are unchanged.
- German/English native renders reviewed. 51 focused tests cover catalogue/launch errors, settings, notebook migration and dirty-note switching, memory, desktop integration and localization.
