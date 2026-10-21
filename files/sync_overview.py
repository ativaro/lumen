"""Shared native settings page; the existing background helpers own all writes."""
from sync_settings import snapshot
from lumen_i18n import tr


def widget(parent, heading=True):
    import json
    import sys
    from pathlib import Path
    from PySide6.QtCore import QTimer, QProcess
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QFrame
    from tools_ui import label, button
    from lumen_i18n import worker_process
    from lumen_apps import launch

    page = QWidget(parent)
    page.setObjectName('syncSettings')
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 8, 0, 8)
    layout.setSpacing(12)
    if heading: layout.addWidget(label(tr('Server & Synchronisation'), 'heading'))
    server = label('', 'muted')
    layout.addWidget(server)
    layout.addWidget(label(tr('Einmal auswählen, automatisch aktuell. Pausieren behält deine Daten. KI-Zugriff wird separat freigegeben.')))
    domains = [
        ('memory', 'Persönliches Gedächtnis', 'Erinnerungen und Kategorien. Keine zusätzliche KI-Freigabe.', 'wissen'),
        ('vault', 'Verschlüsselter Tresor', 'Auch geschlossen und gesperrt. Erste Zuordnung im Tresor einrichten.', 'vault'),
        ('preferences', 'Persönliche Einstellungen', 'Sprache und Desktop-Design. Serverfassung wird übernommen; Änderungen gelten beim nächsten App-Start.', None),
    ]
    checks, statuses = {}, {}
    process = worker_process(page)
    page.process = process
    message = label('', 'muted')
    retry = button(tr('Jetzt abgleichen'), lambda: run(dict(action='sync',manual=True)), 'view-refresh')

    def refresh():
        if process.state() != QProcess.ProcessState.NotRunning: return
        try:
            data = snapshot()
            server.setText(data['server'] or tr('Noch kein Server verbunden'))
            for domain, check in checks.items():
                row = data[domain]
                check.blockSignals(True)
                check.setChecked(bool(row.get('enabled')))
                check.blockSignals(False)
                detail = row['status']
                if row.get('last_sync'):
                    from datetime import datetime
                    detail += ' · '+tr('Zuletzt {0}', datetime.fromtimestamp(row['last_sync']).strftime('%d.%m. %H:%M'))
                statuses[domain].setText(detail)
            roots = data['drive']
            drive_check.blockSignals(True)
            drive_check.setChecked(any(r['enabled'] for r in roots))
            drive_check.setEnabled(bool(roots))
            drive_check.blockSignals(False)
            drive_status.setText(tr('{0} Ordner · {1} aktiv', len(roots), sum(bool(r['enabled']) for r in roots)))
        except Exception:
            message.setText(tr('Abgleichstatus konnte nicht geladen werden.'))

    def run(request):
        if process.state() != QProcess.ProcessState.NotRunning: return
        message.setText(tr('Abgleich wird geprüft …'))
        for check in checks.values(): check.setEnabled(False)
        retry.setEnabled(False)
        drive_check.setEnabled(False)
        process.start(sys.executable, [str(Path(__file__).with_name('sync_settings.py'))])
        process.write(json.dumps(request).encode())
        process.closeWriteChannel()

    def finished(code, _status):
        for check in checks.values(): check.setEnabled(True)
        retry.setEnabled(True)
        raw = bytes(process.readAllStandardOutput())
        process.readAllStandardError()
        try: result = json.loads(raw)
        except ValueError: result = {}
        problem = code != 0 or any(isinstance(value, dict) and value.get('error') for value in result.values())
        message.setText(tr('Abgleich braucht Aufmerksamkeit. Verbindung und Bereich prüfen; Tresor zuerst zuordnen.') if problem else tr('Einstellungen übernommen. Der Hintergrundabgleich läuft für aktive Bereiche.'))
        refresh()
    process.finished.connect(finished)
    process.errorOccurred.connect(lambda error: finished(-1, None) if error == QProcess.ProcessError.FailedToStart else None)

    for domain, title, description, application in domains:
        card = QFrame(page)
        card.setObjectName('syncCard')
        card.setStyleSheet('QFrame#syncCard { border: 1px solid palette(mid); border-radius: 10px; }')
        body = QVBoxLayout(card)
        body.setContentsMargins(14, 10, 14, 10)
        top = QHBoxLayout()
        check = QCheckBox(tr(title).replace("&", "&&"))
        check.setAccessibleName(tr(title))
        check.toggled.connect(lambda enabled, key=domain: run(dict(action='configure', domain=key, enabled=enabled)))
        top.addWidget(check, 1)
        if domain == 'preferences':
            top.addWidget(button(tr('Serverfassung übernehmen'), lambda: run(dict(action='configure',domain='preferences',enabled=True))))
        if application:
            top.addWidget(button(tr('Einrichten / prüfen') if domain == 'vault' else tr('Öffnen'),
                                 lambda _=False, app=application, key=domain: launch(app, area='lumen' if key=='memory' else None)))
        body.addLayout(top)
        body.addWidget(label(tr(description), 'muted'))
        status = label('', 'muted')
        body.addWidget(status)
        checks[domain], statuses[domain] = check, status
        layout.addWidget(card)

    drive_row = QHBoxLayout()
    drive_check = QCheckBox(tr('Ausgewählte Drive-Ordner'))
    drive_check.toggled.connect(lambda enabled: run(dict(action='configure', domain='drive', enabled=enabled)))
    layout.addWidget(drive_check)
    drive_status = label('')
    drive_row.addWidget(drive_status, 1)
    def drive():
        from drive_ui import show
        show(page)
    drive_row.addWidget(button(tr('Drive-Ordner auswählen'), drive, 'folder-cloud'))
    layout.addLayout(drive_row)
    layout.addWidget(retry)
    layout.addWidget(message)
    page.timer = QTimer(page)
    page.timer.setInterval(5000)
    page.timer.timeout.connect(refresh)
    page.timer.start()
    refresh()
    return page
