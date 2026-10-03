# German and English Lumen interfaces

## Objective and boundaries
Add English alongside German to Lumen, Files, search, the native companion tools,
settings/setup and Plasma controls. Shared setting: System language, Deutsch,
English. Language changes apply on next application start, with an explicit
notice; do not restart active editors or replace user content to switch language.
Use the existing PyQt5/Qt/KDE runtime without a new translation service.

Translate product-authored UI labels, guidance, progress and error messages at
explicit source call sites. Never translate paths, identifiers, database keys,
user documents, server text or serialized commands. Keep dictionary keys and
machine enums stable. Parameterized translations preserve every argument and
format specifier. German source text is the fallback; English catalogs are
reviewable UTF-8 JSON in files/translations/en/. Qt's own dialogs follow the same
language. Subprocesses inherit the effective language. English model-response
preferences apply to normal Lumen conversation; explicit user language requests
still take precedence.

## Runtime contract
`from lumen_i18n import tr, language`
`tr('Ordner öffnen')` returns the current translation.
`tr('{0} Dateien', count)` uses positional str.format placeholders. Existing
f-string conversions/specifiers belong in the template, e.g. `{0:.1f}`.
`tr('Hallo {name}', name=value)` supports named placeholders too.
Never wrap an already assembled f-string or user-supplied text in tr.
`language()` returns `de` or `en`, reading LUMEN_LANGUAGE override, then shared
QSettings Lumen/Assistant uiLanguage (`system`, `de`, `en`). The system default
uses German for German locales, English otherwise. `install(app)` loads Qt base
translations. Catalogs are split by source ownership; duplicate keys must agree.

## Implementation and verification
Source follows existing modules and layout conventions. Plain literals and
localized display values remain separate from stored data/selection identities.
Test locale resolution, templates, catalog coverage/placeholders, native English
main surfaces and German regressions. Render representative native windows and
check Plasma texts. Commands:
`PYTHONPATH=files QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de python3 -m unittest discover -s files -v`
`/usr/lib/qt6/bin/qmltestrunner -input plasmoid/tests -platform offscreen`
`./packaging/arch/build-package.sh`
The user bundle must include catalogs; compare installed/package resources.

## GitHub and licensing
Move the install command into the first README screen with correct prerequisites
and private-repository access limits. Confirm remote main after pushing. No
repository visibility or license change without the user's concrete choice.
License advice must distinguish official-project governance from granted rights
to copies/forks and preserve all third-party notices and requirements.
