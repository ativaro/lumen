# Lumen Server entry points

The top-panel app list uses an authenticated `/bridge/me` read, bound to the
current paired device and unchanged server credentials. Only server apps with
current grants appear. Local Lumen, Files and System remain present. There is
no additional app bar or local replacement for disconnected server apps.

Files performs the same bounded check outside its GUI thread every five seconds.
Its Lumen Drive place appears only with the `drive` grant and disappears after a
failed or disconnected check. Places refresh on grant changes only. Existing
tabs, local offline folders, data and drafts are retained. App sessions and
operations still validate authorization independently; visibility is no grant.

Admin and project skills use the server catalogue and exact schemas. The admin
skill describes `lumen_app_diagnose`, its metadata-only results, and the limits
of configuration/assignment checks. Native credential operations remain local.
