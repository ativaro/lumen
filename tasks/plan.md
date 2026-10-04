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
