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
