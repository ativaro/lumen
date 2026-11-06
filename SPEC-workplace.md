> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Der frühere globale Arbeitsraum-/Room-Entwurf ist verworfen. Es gibt keine globale Arbeitsraum-Auswahl; Projekte sind Server-Sammlungen und keine umbenannten Rooms. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# Native workplace

Approved: projects with resume, a shared change history, work modes, shared
transfers and a project overview across local and network storage.

Reuse the existing SQLite settings store, saved file rooms, KIO connections,
native desktop controls and conflict-safe action undo. Append desktop page 8;
existing page indices and external activation remain compatible.

Acceptance:
- A project saves named local/NAS sources, a room, selected installed applications,
  explicit web URLs and a continuation note. Resume restores these on a click.
- Source availability and a bounded recent-file listing are asynchronous. Offline
  sources stay visible; all entries identify their origin. Combined browsing uses
  the existing library view.
- History includes native task edits, file operations and settings changes.
  Undo checks the current state first and refuses to overwrite later changes.
  Unsupported operations remain visible without an undo button.
- Editable work/gaming/travel modes combine optional audio, notifications,
  window layout and selected connections. Failures and partial results are shown.
- Transfers initiated in Lumen share persistent progress. Downloads use HTTP(S),
  staged destinations and guarded range resume; external browser downloads are
  outside this integration. Offline I/O never runs on the GUI thread.
- Native keyboard-accessible UI, isolated behavioral tests, native preview,
  full regression tests and a built package before completion.

Build order: shared history → project persistence/overview → desktop modes →
transfers → native integration → review, verification and packaging.

Panel roles clarified by the user: left is the Lumen system overview; the middle
combines app/file search and conversation in one native surface and one input;
the right contains settings, system controls and themes. No duplicate generic
assistant launchers or separate ask button. Follow-up messages retain the session.
Settings open directly without the full desktop assistant behind them.

Desktop API references: KDE's [notification settings](https://github.com/KDE/plasma-workspace/blob/master/libnotificationmanager/kcfg/donotdisturbsettings.kcfg),
[live configuration watcher](https://github.com/KDE/plasma-workspace/blob/master/libnotificationmanager/settings.cpp),
[KConfig date serialization](https://github.com/KDE/kconfig/blob/master/src/core/kconfiggroup.cpp)
and [KWin window properties](https://github.com/KDE/kwin/blob/master/src/window.h).

## Arbeitsräume: Weiterarbeiten und Werkbank (07.10.2026)

Approved combination: proposal 1 as landing page, proposal 2 inside a room.
Keep the existing Catalog project/room identity, stored tabs, selection, chat,
NAS sources, configured launch actions, guarded history and transfer subsystem.
No content migration or separate task database.

Implemented: featured last room, responsive room cards, compact creation with
name/folder, workbench columns for next step/knowledge, material, conversations
and tasks. Files, Tasks and History tabs retain detailed navigation. Global
transfers/history remain under Activity; work modes remain in Lumen System.

Pins store bounded references: registered file/knowledge objects, validated web
URLs, explicit conversation identity and existing task identity. Removal/reorder
never deletes originals. Live note excerpts are transient (first eight pinned
notes, 350 characters each); reading occurs in a timed worker. Sources do not
claim availability until checked. File pins follow existing relocation registry.
Optional opening on Resume is explicit per file/web pin. Saved application/web
launch preferences continue to apply. Resume preserves the existing room-state
flow; unsent chat replacement requires an explicit choice with No as default.

Discuss opens an editable conversation draft with linked file paths and the
room's next step; it does not submit automatically. Task state comes from the
existing Store. Pins and room edits refuse stale snapshots and refresh the
active-room reference so autosave cannot silently erase them. No new engine,
server synchronization, task execution or Focusroom mode in this UI change.

Verification: test_workplace and test_workplace_rooms; native source/installed
Lumen host navigation and clean exit; DE/EN and dark/light Qt renders. Existing
Files menu, Drive and interop UI checks remain applicable. Direct installer
already includes new Python modules and translation catalogs by directory.
