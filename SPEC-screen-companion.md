# Screen companion

Accepted first version: select one window, state a goal, receive one next step at a time in a small native sidecar; continue by text or existing local voice. The user operates the target application. No execution tools, mouse control, automatic learning, or whole-desktop capture.

- KWin selects a window; every subsequent capture uses that UUID. No active-window fallback. Closed/minimized/protected windows stop capture.
- Images remain local until explicit consent. Provider notice explains remote transmission and engine/provider history. First image is always reviewed. Unsupported accessibility protection requires review for each image.
- Optional change monitoring checks at most once every 5 seconds, requires stable changed frames, only one inference in flight, and a finite session limit. Visible password roles pause capture; unavailable or ambiguous accessibility state stops automatic sending. This is not a universal secret detector; visible tokens/unmarked fields require user caution and pause.
- Pause/end cancel pending capture and generation; stale results cannot submit. Temporary local images are removed after inference/stop.
- Native themed UI: selected window, goal, local preview, next step, microphone with activity, pause, end. Enter sends; Shift+Enter adds a line.
- Integration: existing screen context menu, Apps/Search catalogue, command launcher; installer and package install it.

Validation: synthetic headless KWin window capture and target identity, changed-frame stability, inaccessible/password guard, no-tools/no-memory backend, pause/late completion, installer presence. No user desktop captures or real provider calls in tests.

Implementation notes: a dedicated dynamically linked Qt/DBus helper declares its
own `org.kde.KWin.ScreenShot2` interface permission. General Python interpreters
receive no capture permission. The helper validates the window UUID and
terminates when its parent dies. Images pass through pipes/data URIs,
not screenshot files. Source contracts: [KWin 6.7 screenshot API](https://raw.githubusercontent.com/KDE/kwin/Plasma/6.7/src/plugins/screenshot/org.kde.KWin.ScreenShot2.xml)
and [window selection](https://raw.githubusercontent.com/KDE/kwin/Plasma/6.7/src/org.kde.KWin.xml).

Verified with synthetic KWin/OpenGL windows, local
preview, pause/late results, invalid window IDs, typed password roles and guarded
backend requests. The isolated KDE session exposes unknown AT-SPI state and
correctly requires manual review. Real cloud inference and microphone hardware
were not exercised by these tests. Existing voice and assistant tests also pass.
