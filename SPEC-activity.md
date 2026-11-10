# Transfers and history

Approved: a shared change history and shared transfers across local and network
storage, opened from Lumen Files.

Reuse the existing SQLite settings store, KIO connections and conflict-safe
action undo.

Acceptance:
- History includes native task edits, file operations and settings changes.
  Undo checks the current state first and refuses to overwrite later changes.
  Unsupported operations remain visible without an undo button.
- Transfers initiated in Lumen share persistent progress. Downloads use HTTP(S),
  staged destinations and guarded range resume; external browser downloads are
  outside this integration. Offline I/O never runs on the GUI thread.
- Native keyboard-accessible UI, isolated behavioral tests, native preview,
  full regression tests and a built package before completion.

Build order: shared history → transfers → native integration → review,
verification and packaging.

Transfer and history records live in the settings store under the `transfer/`
and `history/` key prefixes (`files/lumen_transfers.py`, `files/lumen_history.py`).

Panel roles clarified by the user: left is the Lumen system overview; the middle
combines app/file search and conversation in one native surface and one input;
the right contains settings, system controls and themes. No duplicate generic
assistant launchers or separate ask button. Follow-up messages retain the session.
Settings open directly without the full desktop assistant behind them.

Verification: isolated transfer and history tests; native source/installed
Lumen host navigation and clean exit; DE/EN and dark/light Qt renders. Existing
Files menu, Drive and interop UI checks remain applicable. Direct installer
already includes new Python modules and translation catalogs by directory.
