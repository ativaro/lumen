# Lumen Studio

Implement the selected Studio reference: 224px quiet navigation, central chat,
resizable optional file preview. Use current theme palette and real existing
backends; no mock folders, task progress or fabricated file metadata in production.

Keep existing page indices/CLI/D-Bus routes, tools, permissions, recovery, persona,
memory and voice behavior. Three primary navigation destinations and recent actual
sessions; supplementary destinations remain in More and Apps. Compact single
composer with context menu, live speech controls and send. Explicit successful
`lumen_present_files` tool results drive the shared image/PDF/text preview and
bounded image thumbnail strip. Attachments are input context, not preview output.
Presentation results belong to their conversation, survive recovery and reopen
from tool history. Repeated polls retain selection/closed state; a new tool result
refreshes even the same path. Only existing regular local/mounted files, max 100;
no extracting paths from prose, URL fetching or automatic file execution.

Preview can be closed/reopened and collapses on small windows; source is never
changed by viewing. Reuse asynchronous file workers so mounted NAS reads cannot
block the UI. Preserve Markdown safety and all existing output actions. German
and English, all themes. Isolated UI tests and native screenshots with synthetic
data verify layout, session navigation, busy state, file selection, preview close,
resize, permission controls and unchanged assistant flows before local rollout.
