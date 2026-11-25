> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Bibliotheken und Sammelfläche bestehen weiter. Die alten Theme-Namen sind überholt und dürfen nicht wieder eingeführt werden. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# File spaces — approved in chat, 2026-09-30

The user approved the suggested libraries and shelf, and added a request for
combined local/NAS folders under Documents, Pictures, Music and custom places.
Native PySide6 controls; originals stay in place; no inference is needed.

| Capability | Responsibility | Depends on |
| --- | --- | --- |
| libraries | Named sets of local/network sources, unified list/grid, visible origin | existing KIO and file views |
| shelf | Persistent references collected across directories, batch actions | libraries' reference and listing support |

Build order: libraries → shelf. These are one cohesive extension to the
existing Files UI, shared with Lumen's integrated Files page.

## Acceptance and boundaries

- Default Documents/Pictures/Music/Videos entries support multiple named sources;
  custom libraries can be created, renamed and removed. Settings and context
  menus expose source management, including network URLs without passwords.
- Unified views list each source's immediate children, keeping equal names
  separate. A visible origin column and a second grid label identify sources.
  Search runs across sources and subfolders. Directories open in their source.
- Sources load independently off the GUI thread; missing or offline sources are
  shown as errors without losing available results. Cancellation/navigation and
  closing ignore stale results. Lists/searches have explicit bounds.
- The virtual view has no implicit write destination: paste, drops and mkdir
  ask for a concrete destination. Intelligent rename/sort stay within each
  selected file's source directory, explicitly labelled. Existing guards remain.
- Shelf supports drag/drop and selection actions, persistent deduplicated file
  references, opening, preview, copy to a chosen folder, rename and Lumen actions.
  Removing a reference never deletes its file. Unavailable references remain.
- Three approved application designs (clear, warm studio, graphite) and optional
  KDE system style share native layout and update live. Compact chat controls
  retain readable labels and expose secondary actions through native menus.
- SMB server roots list shares as folders without requiring a share name or an
  extra connection form. Opening a protected share invokes native KDE login when
  needed. New connections only need the server address; full share URLs still work.
  KDE handles usernames/passwords;
  mount success alone is insufficient: a real directory read must succeed first.
  Existing `kioclient --interactive ls` provides native authentication before
  SMB mounting, including older KIO-FUSE without a GUI job delegate.
- Local and network locations remain canonical, not transient KIO mount paths.
  Store metadata via the existing SQLite settings table, per object and transaction.
- No new dependencies, background content indexing, automatic synchronization or
  system/desktop changes. Test with isolated state and local WebDAV fixtures.

## Implementation and verification

`files/file_spaces.py`: catalog persistence and source listing processes;
`files/file_spaces_ui.py`: native controller/UI. `files/app.py`: virtual navigation and existing file action hooks.
Existing Python
style (four spaces, native Qt signals); reuse Network, Store, FileWorker and views.
Focused tests: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s files -p 'test_file_spaces.py'`.
Full tests: the isolated run of PUBLISHING.md ("Verify locally").
Validate rendered light/dark native views, a real local WebDAV source, package
contents, and installed entrypoints. Update README/guide and system/sync records.

## Delivery checklist

- [x] Libraries and origin-preserving listing/search, persistence and tests.
- [x] Shelf collection and native batch operations.
- [x] Independent review, full tests, visual inspection, install and documentation.
