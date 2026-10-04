# Readable Lumen responses and interactive results

Chosen: calm typography (variant1) and precise tables (variant3), preserving existing
palettes. Default Adwaita Sans with font fallback, 17px body, 1.5 line spacing, readable
line length, unboxed assistant text. Shared adjustable 14–22px text and comfortable /
compact density in Appearance settings, live in Search and Studio. No lost controls.

One bounded declarative MCP view tool selects native components independent of language:
tables (sort/filter/selection/copy/CSV), numeric sliders with direct input, choices,
switches, horizontal bar charts, reported progress and file cards. Shared Qt Quick
renderer in Search and embedded in Studio; no model-supplied HTML, QML or scripts.
Existing plain answers and explicit file preview continue to work. Components must
show real tool data, never synthetic data outside tests and designs.

Only completed tool results in the owning conversation render. Repeated polls retain
edits and table state. New results/sessions reset appropriately; recovery preserves
values but never submits. Submit is an explicit structured follow-up using the normal
backend, respecting mode, busy state and permissions. No action while dragging a
slider. File opening/export are explicit user gestures; CSV export preserves existing
files and escapes spreadsheet formulas. Bound counts, text and numeric ranges.

Verify model/tool contract, GUI interaction in both surfaces, narrow layouts, themes,
DE/EN, scaling, recovery, request controls and a real-engine synthetic round trip.

## Follow-up selected Search reference

After components, replace the compact Search home with the user's overview design:
centered tabs Overview/Tasks/Conversations, large unified composer, six app shortcuts,
real task list and recent desktop documents, quiet status footer and settings/window
controls. Existing search results, chat, voice, permission questions, persona/session
selection and drafts remain available. Responsive two-column overview collapses at
small width. App routes use existing launchers; task opening never approves work.
Dismiss only completed/cancelled tasks through Store. Recent files from local XBEL/
KDE recent records, no recursive scan or network stat. Read snapshot in bounded worker,
refresh while visible only; never claim system health without a diagnostic result.
