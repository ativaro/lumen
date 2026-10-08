# Unified search with Qt 6 / QML

1. Isolate a pilot checkout and document the comparison contract.
2. Extract nonvisual jobs and voice state; let the shared backend run with either
   explicitly loaded Qt binding. Verify existing Qt 5 behavior.
3. Build the Qt 6 controller and polished QML search/conversation surface using
   existing themes, language and permission semantics.
4. Verify keyboard, file search, conversations, recovery, permissions, voice and
   visual states using local mock services and temporary state.
5. Package an optional pilot starter, benchmark both implementations, install and
   show the pilot for comparison; document measured limits and commit the work.

# Interoperability (user-approved 2026-10-03)

Implement the numbered cross-app scenarios in vertical slices, following docs/interop/CONTRACT.md. Shared references/dispatch precede independent source/destination, backup, and audio work. Integrate each completed path into native menus, test against temporary stores, then verify cold/warm launch and update the installed user runtime. Track exact requirement evidence in docs/interop/COVERAGE.md, rather than counting generic actions as finished workflows.

# Personal learning (2026-10-04)

Implement docs/memory/LEARNING.md in the existing memory pipeline. Semantic intent
classification belongs to the configured LLM, not word filters. Validate structured
results, reuse existing editable notes and expose the global profile in Wissen.
Verify storage/backend/native UI and multilingual inference before rollout.

# Guided backups (user-approved 2026-10-05)

Build the approved four-step native Vault backup wizard: Files/Lumen/encrypted
Vault sources, discoverable local/SMB destinations with inline credentials and
keyring retention, daily catch-up and independent recovery key, first real backup
plus test restore. Follow with three coverage cards and safe restore/adoption.

1. Backend source inventory and stable encrypted Vault snapshot; test with synthetic
   stores and real Restic. Keep old plans compatible.
2. Network discovery/mount/test worker: no credentials in argv, URLs, plans or logs;
   explicit remember checkbox; persist endpoint/identity, remount on runs.
3. Four native wizard pages, DE/EN, asynchronous tests; recovery key acknowledgement;
   honest partial/offline states and initial restore probe.
4. Coverage cards, restore entry in setup and existing-repository recovery, second
   destination via same wizard. Never overwrite existing data during restore.
5. Native/UI/regression verification, security review, package/runtime rollout and
   private Git update. Actual personal backup requires the user's destination/key
   choices in the wizard; tests use only temporary synthetic repositories.

Risks: offline mount must not create a local shadow repository; stable Vault inode
copy must never decrypt; recovery key must be independent of the backed-up Vault;
partial Restic results must never be advertised as complete. USB identity/repository
identity checked on every run. Discovery absence exposes manual server entry.

# Eigener PDF-Kern (Nutzerentscheidung 2026-10-05)

Siehe SPEC-pdf-core.md. Eigenständige, begrenzte PDF-Verarbeitung zuerst an
synthetischen Dateien prüfen; danach Rendering/Text, sichere Seitenexporte und
Übersetzung. Erst nach bestandenen Kompatibilitätsprüfungen Reader/EPUB/HTML,
Notizanker, Suche/Vorschau und Paketabhängigkeiten umstellen. Bestehende offene
Aufgaben anderer Arbeitsbereiche bleiben erhalten.
