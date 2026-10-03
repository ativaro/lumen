# Lumen Qt 6 migration

## Approved objective
The user accepted the QML search pilot and requested switching everything.
Move every Lumen-owned GUI and its tests from PyQt5 to PySide6/Qt 6, make QML
search the production search, and migrate launch/install/update paths together.
Python remains the backend. Existing rich file/tool views remain native Qt 6
widgets during this framework migration; do not remove working features for a
cosmetic rewrite. Shared settings, data, shortcuts and desktop identities survive.

## Plan and acceptance
1. Port shared services, main/Files, settings/setup, nine companion apps and
   integration dialogs to PySide6. No production PyQt import or dual Qt process.
2. Fix Qt 6 differences explicitly: signals, enums, D-Bus replies/metadata,
   ownership, event coordinates, MIME/icon/model behavior and native activation.
3. Promote QML search behind the existing launcher/service/shortcuts. Keep its
   draft/session checkpoint; preserve a pre-existing production draft on upgrade.
4. Update all launchers, subprocess workers, bootstrap and package dependencies.
   System PySide6 or one shared user runtime must work across every start route.
5. Run the isolated regression suite, GUI/interaction and cold/warm launch tests;
   render main/Files/settings/search and companion windows in both languages.
6. Build and verify the package. Back up local program files and SQLite stores,
   install the user bundle, preserve active work and perform a verified handover.
   Update private system references and private GitHub after reviewing source.

## Checks
Runtime during development: `~/.local/share/lumen/qt6-env/bin/python`.
Full tests: a temporary HOME/XDG profile, `LUMEN_LANGUAGE=de`,
`QT_QPA_PLATFORM=offscreen`, a separate `dbus-run-session`, then
`python -m unittest discover -s files -v`. Optional engine integrations retain
their explicit prerequisites. Qt6 QML lint and native Wayland captures complement
tests; use synthetic fixtures and mock HTTP for model/permission checks.

## Boundaries
Preserve unrelated changes and all user data. No license replacement, automatic
LLM requests, system package removal or database format changes. Older installed
Qt5 libraries may remain for unrelated applications. Report migration limitations
honestly; a binding migration alone is not a full QML rewrite of every screen.

## Verification recorded during migration
- 349 isolated tests: 344 passed; five optional Restic/CalDAV integrations skipped.
- Real cold/warm search, D-Bus singleton, killed-process checkpoint recovery;
  all nine companion launchers, Reader/Wissen forwarding and reviewed handoffs.
- 28 DE/EN window renders; main, Files and search additionally rendered under
  native Wayland. QML lint, Python and shell syntax passed.
- Qt 6 API fixes include D-Bus replies, signal metadata/receiver signatures,
  icon-provider enums, flag combinations and consistent worker interpreters.
  Worker save acknowledgements now release the GIL while awaiting GUI replies;
  canceling memory preparation does not send an abort to an old session.
- Retired the widget search implementation. QML tests cover its keyboard/file,
  conversation, voice, theme, permission and recovery contracts.
- Offscreen clipboard data is explicitly released by its test; preview-width
  persistence is measured at equal window dimensions because Qt 6 constrains
  restored geometry to the test screen.
- Final installation checks also covered a fresh, isolated Plasma session and
  repeated desktop setup. Existing service templates retain custom fields and
  backups when their interpreter is migrated. Installed launchers and package
  payloads were verified separately from the source tests.
