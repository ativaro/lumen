# Lumen Files startup

2026-10-05 · Linux x86_64, Python 3.14, PySide6/Qt 6.11.2.

Measure from invoking `bin/lumen-files` until the 250-file listing has painted
and the GUI processes another event. Includes the runtime check, crash supervisor,
imports, preferences, database initialization and filesystem model. Disposable
configuration and data; one warm-up followed by seven fresh processes with warm
filesystem caches. These are not post-reboot cold-cache measurements.

| Change (cumulative) | Median, offscreen | Slowest of 7 | Decision |
| --- | ---: | ---: | --- |
| Before | 397.14 ms | 400.49 ms | Baseline |
| Keep the crash supervisor free of Qt/storage imports | 363.22 ms | 382.26 ms | Keep |
| Import Gio when moving a file | 326.10 ms | 330.13 ms | Keep |
| Skip setup-dialog imports after completed/deferred setup | 310.87 ms | 323.58 ms | Keep |

Wayland desktop validation with the same workload: **388.35 → 312.57 ms** median
(19.5% less time), maximum **393.78 → 317.55 ms**. The original installed launcher
was measured before replacing any runtime files. No multi-second startup stall
was reproduced with these local directories.

`cProfile` identified import work on the startup path: the crash supervisor pulled
in the store's translated constants and therefore Qt before starting the GUI;
Files also loaded Gio despite only needing it for moves, and loaded the entire
setup/settings implementation even for an already configured profile. The shared
state-directory resolver now lives in a small module; existing store imports keep
working. Translation happens when crash messages are shown.

## Repeatable checks

```sh
python3 tests/check-files-startup.py
python3 tests/check-files-startup.py --platform wayland --binary "$HOME/.local/bin/lumen-files"
QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de python3 -m unittest discover -s files -p test_crash.py
```

The startup check fails above 1000 ms in any measured sample; use `--budget-ms`
to set an appropriate budget on another machine. Keep the platform, interpreter,
workload and sample count fixed for comparisons. The test-only paint observer is
injected into the real GUI child; production needs no benchmark hooks or cache.
The import regression test separately prevents eager Qt/storage loading in the
supervisor and eager Gio loading in Files. Existing Files tests cover navigation,
restoring tabs, search, previews and file operations; crash tests cover monitoring,
recovery and safe restart. The real app entry point was also exercised for first
setup, an already configured profile and explicit settings.

Two broader `test_lumen_os` failures were reproduced from unchanged `cf1cc4a`:
`test_native_pages_workflow_result_and_source_context` and
`test_cached_vision_launcher_reaches_current_app_and_preserves_arguments`.
The unrelated Companion settings/catalog error found during validation is fixed
by the separately merged upstream commit `8ef0d25`.
