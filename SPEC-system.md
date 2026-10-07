# Lumen System

## Objective and accepted design
The user approved the calm hardware overview and detailed activity mockups, naming
the standalone application **Lumen System**. Overview is the default, Activity and
Devices are secondary views. Use shared Lumen typography and all four themes.
CPU, GPU, memory and root storage cards show real values, supporting sensor values
and small histories. Activity shows timed charts, current-user processes and
measurement events. Devices reveals the complete available sensor list.

## Architecture and boundaries
Python/PySide6 + native QML; no new dependencies. A separate, bounded worker samples
Linux /proc every two seconds and optional sensors/NVIDIA tools every ten seconds.
The GUI never waits for sensors or scans network filesystems. One hour of history
is kept only in memory while the application is running. Missing/reset counters
produce gaps, never fabricated zeros. Process CPU is percent of one logical core;
system CPU is percent of the whole machine. No commands, environment, file names
or other users' process details are collected. Storage describes / explicitly.
Events identify measured threshold crossings, not inferred causes. GPU utilization
supports NVIDIA and exposed AMD sysfs counters; sensor support depends on drivers.

Integrate app catalogue, panel hardware route, desktop launcher, installers and
settings. Preserve background-work policies. A read-only MCP snapshot exposes the
same measurements. “Mit Lumen prüfen” sends a clearly identified measurement
snapshot on explicit click; no automatic AI calls or system changes.

Always verify native runtime, DE/EN and themes; never commit private data or copy
Numen code under unresolved licensing. Existing user approval covers implementation
of this design and routine integration; do not add privileged tuning or termination.

## Implementation order / verification
1. `files/system_data.py`: sampler; unit tests for deltas, PID reuse, resets and gaps.
2. `files/system_app.py`, `files/qml/system/`: asynchronous controller and UI,
   native click tests and screenshots at normal/narrow sizes in four themes.
3. Catalogue/settings/launcher/MCP/installers; integration and regression tests.
4. Documentation, package, local install and launch verification.

Commands (from repo):
`PYTHONPATH=files python -m unittest files/test_system_data.py`
`python /tmp/run-wissen-layout.py test_system_ui test_settings_navigation test_app_center`
`bin/lumen-system`
`./packaging/arch/build-package.sh`

Code follows existing Python modules: small named functions, plain bounded dict
payloads and explicit read errors, e.g. `cpu = usage(previous, current)` returning
`None` for unavailable intervals. Tests live in `files/test_system_*.py`.

## Acceptance
All launch routes open one native Lumen System window. Overview, chart ranges,
process sorting, pause/resume and device expansion work. Empty/unavailable readings
are understandable and stale data is identified. Closing the app stops its worker.
Settings retain existing policies. Package and user installation include every asset.

## Verification record
- Counter/PID/reset/privacy/MCP tests: 6 passed.
- Native QML clicks, worker lifecycle, stale/pause, explicit analysis and settings
  launch/policy tests: 5 passed; existing app/navigation tests: 12 passed.
- Native MCP and settings regressions: 27 passed.
- DE/EN screenshots inspected in Glass, Graphite, Atelier and Midnight;
  responsive 820×620 layout verified. No mock data is part of the runtime.

### Settings activation correction
Clicking Lumen System in Apps, Maintenance or the settings search opens the app
immediately and reveals its background preferences underneath. Programmatic
settings navigation and searches targeting a specific setting do not launch it.
Launch errors remain visible in the settings status. Native pointer regression
and real desktop cold-launch verification pass; 19 related UI tests pass.

### Plasma control-panel dispatch correction
The user clarified the failing entry was in the small upper-right panel. Its
root action allowlist omitted `hardware`, so no helper was invoked. Admit the
hardware action and allow app launches during periodic status reads; volume,
brightness and mute remain serialized. Regression executes the actual main.qml
JavaScript handler and a native ControlCenter pointer test covers the emitted
action. The prior settings-window correction did not cover this distinct route.
