> Historical pilot specification. The production migration is specified in [SPEC-qt6.md](SPEC-qt6.md).

# Qt 6 / QML search pilot

## Objective and approved scope
A separately launchable, working comparison of the unified Lumen search in
Qt 6/QML with the existing Python engine. The user approved the pilot after the
language/licensing discussion. Keep one composer for search and conversation;
retain local voice, permission/question replies, task tracking, themes, language
and session drafts. The existing production search and shortcuts remain available
while the pilot is evaluated. No license replacement or broader app rewrite.

## Structure and dependencies
- `files/search_qml.py`: Qt 6 entrypoint and desktop activation.
- `files/search_controller.py`: asynchronous search and conversation state.
- `files/qml/search/`: native Qt Quick controls and presentation.
- `files/lumen_qt.py`: shared nonvisual Qt APIs, selected by the entrypoint's
  already imported binding; never load Qt 5 and Qt 6 together.
- `files/voice_session.py`, `files/lumen_jobs.py`: existing voice/job behavior
  extracted from widgets, reused by the Qt 5 and Qt 6 surfaces.
- PySide6 Essentials 6.11.2 in an optional user-local environment; no sudo.
- Python unittest and QtTest with temporary settings/data and synthetic inputs.

## Commands
- Pilot: `bin/lumen-search-preview`
- Install optional runtime: `bin/lumen-search-preview --install-runtime`
- Qt 6 tests: `QT_QPA_PLATFORM=offscreen ~/.local/share/lumen/qt6-env/bin/python -m unittest discover -s files -p test_search_qml.py`
- Qt 5 regression: use the isolated profile/D-Bus command in `PUBLISHING.md` with `LUMEN_LANGUAGE=de`; set `LUMEN_QT6_PYTHON` to the optional runtime to include the pilot checks.
- Benchmark: `tests/benchmark-search.py` (isolated settings/data, synthetic directory;
  reports first frame, resident memory and input-to-results separately).

## Implementation and style
Use QObject signals/slots for backend state and declarative QML presentation.
Bound filesystem work in subprocesses and keep the existing authenticated local
OpenCode client. Reuse the existing theme tokens and translation catalog. Match
Python snake_case and the repository's unittest conventions. Example:

```python
@Slot(str)
def set_query(self, text):
    self._query = text
    self.queryChanged.emit()
    self.debounce.start()
```

## Acceptance and verification
1. Enter activates the currently selected fresh result; Ctrl+Enter starts a
   conversation in place; arrows, Shift+Enter, Tab and Escape work.
2. Real local file/application results; stale scans cannot overwrite newer queries.
3. Follow-up replies preserve the session, tool approvals and multi-question
   responses are usable, stop/reset and error recovery work without resending.
4. Voice uses the existing recognition/TTS configuration, visible activity and
   interrupt; hiding the window releases the microphone.
5. Four themes and German/English render without QML warnings; narrow view and
   long text stay usable; untrusted content cannot load local/remote images.
6. User draft/session recovery persists locally and never restarts an operation.
7. Native rendered screenshots and reproducible first-frame/RSS/search timings
   compare the two implementations; report regressions honestly.
8. Optional launcher/install assets work from source and the user bundle.

## Boundaries
Always use temporary data for automated tests and preserve live user drafts.
Keep the pilot opt-in. Do not change the existing hotkeys or send synthetic tasks
to the real LLM. Do not commit user config, runtime environments or screenshots.
