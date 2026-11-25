# Lumen conversation scrolling

New user turns start at the top; answers grow below them without chasing the end.
Typing, tables and incremental results preserve the reading position. Scrolling
or explicitly jumping to the latest text detaches the initial turn anchor. A
latest-message control appears while real content remains below the viewport;
reserved blank space is not treated as a new message.

Qt Studio and QML Search keep stable message rows and reserve only the space
needed to place a short user turn at the top. Layout changes remeasure that
anchor only until the reader scrolls. Existing chronological rich results,
clipboard handling, answer actions and the installed save-as-tool action remain.
The plain Files assistant uses a document bottom margin for the same short-turn
placement; it preserves its offset during later answer updates.
