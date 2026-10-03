# Qt 6 desktop and QML search

The search pilot is now the normal `lumen-search`. The panel, existing keyboard
shortcuts and microphone use `org.lumen.Search` and the same search window.
`lumen-search-preview` remains a compatibility alias; it no longer adds a second
application to the menu. Its earlier Qt 5 comparison is preserved in Git history.

All Lumen-owned desktop programs now use PySide6/Qt 6. Search uses QtQuick/QML;
Files, the main window, settings, setup and companion apps use Qt 6 Widgets.
Python remains the backend. OpenCode remains a separate engine process.

## Runtime

On Arch/CachyOS, the installer uses `python-pyside6`. Alternatively install the
shared user runtime without replacing system Python:

```bash
bin/lumen-python --install-runtime
bin/lumen-search
```

This installs PySide6 Essentials 6.11.2 in
`${XDG_DATA_HOME:-~/.local/share}/lumen/qt6-env`. Every Lumen launcher uses
`lumen-python`: an explicit `LUMEN_PYTHON` override, compatible system Python,
then this user runtime. Workers inherit the chosen `sys.executable`. The runtime
uses system site packages for existing GIO, Pillow and other dependencies. Do not
remove it while applications are running or before installing system PySide6.

## Preserved behavior

- Applications and bounded filename search, keyboard selection, opening files.
- A single composer for queries and continued conversation, rendered replies,
  session switching, read/fix modes, explicit tool permissions and questions.
- Dictation/conversation, microphone level indicator, interruption and stop on hide.
- Shared themes, language, model policy, task history and local memory controls.
- The usual draft checkpoint at `${XDG_STATE_HOME:-~/.local/state}/lumen/search.json`
  (or `LUMEN_DATA`). On the first migration only, the previous preview checkpoint
  is used if no regular checkpoint exists. Restoring never resends a request.

The migration does not change personal database formats or the project license.
Dependency licensing is tracked separately in [LICENSE-PLAN.md](LICENSE-PLAN.md).

## Verification

Use a temporary HOME/XDG profile and a separate D-Bus session:

```bash
bin/lumen-python -m unittest discover -s files -v
dbus-run-session -- bin/lumen-python tests/check-search.py
bin/lumen-python tests/benchmark-search.py --samples 5
```

Set `QT_QPA_PLATFORM=offscreen` and `QT_QUICK_BACKEND=software` for headless tests.
`test_search_qml.py` exercises actual rendered QML keyboard/forms/voice controls
and a mock HTTP engine. `test_search.py` verifies normal/preview draft precedence
and external theme updates. `check-search.py` verifies real cold/warm launch,
D-Bus identity, process supervision and recovery after a killed search process.
