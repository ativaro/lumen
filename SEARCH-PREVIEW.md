# Qt 6 search preview

This opt-in pilot evaluates a native QML interface with the existing Python
engine. Open **Lumen Search Preview** from the application menu, or run
`lumen-search-preview`. The regular search, panel and shortcuts continue to use
the established Qt 5 interface. No global migration is required to try it.

## Runtime and source launch

The usual Lumen dependencies are still needed, including PyGObject for application
discovery. If the system already supplies PySide6/QtQuick/QtDBus, the launcher uses
it. Otherwise install the optional user-local runtime:

```bash
bin/lumen-search-preview --install-runtime
bin/lumen-search-preview
```

This installs PySide6 Essentials 6.11.2 into
`${XDG_DATA_HOME:-~/.local/share}/lumen/qt6-env`, using a virtual environment that
can access the system's Python modules. It requires Python's `venv`/`ensurepip`
support, internet access and disk space; it does not use sudo. On Arch, the
optional `python-pyside6` system package is another route. The normal installer
copies the QML resources and menu entry but does not download this runtime.

## What works

- One input for applications, local files and follow-up conversation. Enter
  activates the current result; Ctrl+Enter asks Lumen, Shift+Enter inserts a line,
  arrows select results and Escape hides the window.
- Existing authenticated OpenCode engine, task tracking and memory integration;
  native tool approvals, multiple questions, free-text replies, stop and history.
- Existing local dictation and speech configuration, microphone activity and
  interruption. Hiding the window stops microphone capture.
- Shared Glass, Graphite, Atelier and Midnight themes, plus German/English.
  Theme changes apply live; language follows the existing app-start convention.
- Local draft/session restoration. The preview checkpoint is
  `${XDG_STATE_HOME:-~/.local/state}/lumen/search-preview.json` (or `LUMEN_DATA`).
  Restoration never re-sends a prompt or restarts an operation. Existing crash
  monitoring and reports are also reused.

The optional service is `org.lumen.SearchPreview`, separate from production
search. Theme, permission and voice preferences remain shared Lumen settings;
changing “Don't ask again” therefore also affects other Lumen windows.

## Comparison and current limits

Five fresh processes per implementation, warm filesystem cache, offscreen
software rendering, 2,000 synthetic files and no LLM request produced these
medians on the development machine:

| Measurement | Qt 5 widgets | Qt 6/QML pilot |
| --- | ---: | ---: |
| Imports to first captured frame | 109.4 ms | 134.8 ms |
| Resident memory after first frame | 91.1 MiB | 119.9 MiB |
| Input to completed file results | 263.9 ms | 267.8 ms |

Search includes the 220 ms typing debounce. These are controlled local comparison
measurements, not cold desktop startup or GPU performance claims. The pilot
currently costs roughly 29 MiB more memory and 25 ms more to its first frame.
It offers a more flexible presentation layer; it is not a demonstrated speedup.

Search scans a bounded part of the personal folder with up to 100 file results
and an eight-second time limit; it is not a full-disk or NAS index. Voice quality
and model latency remain those of the existing engines. This is a search pilot,
not a conversion of Files, every companion app or all dependencies away from
PyQt. No project license was changed by this experiment.

## Reproduce checks

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -p test_search_qml.py
tests/benchmark-search.py --samples 5
QT_QPA_PLATFORM=offscreen ~/.local/share/lumen/qt6-env/bin/python tests/render-search-qml.py
dbus-run-session -- /usr/bin/python3 tests/check-search-preview.py
```

Set `LUMEN_QT6_PYTHON` for a different test runtime. The native tests exercise
keyboard and mouse interaction, HTTP permission/question replies, cancellation,
safe message rendering, themes and session restoration in temporary profiles.
The renderer uses synthetic examples and writes ignored artifacts. Use the
isolated profile/D-Bus command in [PUBLISHING.md](PUBLISHING.md) for the full suite.

Remove the optional runtime only after closing the preview; ordinary Lumen does
not depend on it. The production search remains available as `lumen-search`.
