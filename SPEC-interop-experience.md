> **Historischer native App-Vertrag.** Notes, Projekte, Code, Inbox, Audio Studio und Vault verwenden heute den gemeinsamen Server-Host. Die früheren lokalen Empfänger und ihre Sicherungs-/Notizordnerabläufe sind kein zusätzlicher Offline-Modus. Aktuelle Übergaben und offene Anschlussgrenzen: [Interop-Bedienung](docs/interop/USAGE.md).

# Contextual Lumen actions

Replace the added integration chrome with useful actions on the selected content.
Keep durable references, save barriers, reviewed writes, recovery and undo intact.

Acceptance:
- No global “Lumen verbinden” menu or separate reference-drag button.
- Files offers one direct Reader action, meaningful content actions and no action
  that simply opens Files again. Ordinary document opening needs no extra review.
- Reader selection/annotations offer “Als Notiz speichern …”; review asks for a
  title and notebook folder. The resulting note links to the exact named source
  page. No date or transfer-mode field appears for a selected quote.
- Knowledge offers notebook backup in its existing settings, including a schedule
  and truthful status. A configured plan must never be presented as a completed
  backup. Existing plans and the native encrypted-target setup remain supported.
- Other content actions remain reachable through native context/existing menus,
  with meaningful labels and only applicable targets. Objects themselves can be
  dragged; the destination determines its matching action.
- Writes name their outcome; source links name their content. Visible copy/link
  decisions describe their effects. German and English are supported.

Verify real native flows using synthetic data, including request delivery and
target persistence, saved edits, cancel, source navigation and backup scheduling.
Install changed production files only after review/checks, with a private backup.
