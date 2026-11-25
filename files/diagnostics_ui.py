"""Local recovery view. Its public status check uses Qt's own HTTPS on purpose, so it still answers when
lumen-service or the rest of Lumen is broken; it sends no credentials. For the paired server it also trusts
that pairing's `ca_file` (private Lumen CA)."""
import json
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest, QSslCertificate
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QWidget
from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
from lumen_i18n import tr
from server_app_session import origin, SessionError


def text(value):
    item = QLabel(tr(value)); item.setWordWrap(True); item.setTextFormat(Qt.PlainText)
    return item


def field(layout, caption, edit):
    """Panorama form field: a 12px caption directly above its input."""
    group = QVBoxLayout(); group.setSpacing(8)
    label = text(caption); label.setStyleSheet('font-size:12px'); label.setBuddy(edit)
    group.addWidget(label); group.addWidget(edit); layout.addLayout(group)


class DiagnosticsView(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Lumen · Hilfe & Diagnose')); self.resize(720, 660)
        self.setMinimumWidth(320)
        self.network = QNetworkAccessManager(self); self.pending = None
        outer = QVBoxLayout(self); outer.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN); outer.setSpacing(PAGE_SPACING)
        outer.addWidget(AppHeader(tr('Was funktioniert gerade?'), tr('Diese lokale Ansicht bleibt ohne KI und Serveranmeldung verfügbar. Serverinterne Prüfungen übernimmt der unabhängige Diagnosezugang.'), self))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame); outer.addWidget(scroll, 1)
        content = QWidget(); scroll.setWidget(content)
        root = QVBoxLayout(content); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(PAGE_SPACING)
        self.server = QLineEdit(); self.server.setAccessibleName(tr('Lumen-Server')); self.server.setPlaceholderText('https://lumen.example.org'); field(root, 'Lumen-Server', self.server)
        self.paired = (None, None)
        try:
            import lumen_connect
            config = lumen_connect.read_config()
            self.paired = (origin(config['server']), config.get('ca_file') or None)
            self.server.setText(self.paired[0])
        except (OSError, ValueError, KeyError, SessionError): pass
        self.check = QPushButton(tr('Öffentlichen Status prüfen')); self.check.setObjectName('primary'); self.check.setAutoDefault(False); self.check.clicked.connect(self.run); root.addWidget(self.check, 0, Qt.AlignLeft)
        self.status = text('Noch nicht geprüft. Es werden keine Anmeldedaten gesendet.'); self.status.setAccessibleName(tr('Prüfergebnis')); root.addWidget(self.status)
        self.recovery = QLineEdit(); self.recovery.setAccessibleName(tr('Unabhängiger Diagnosezugang')); self.recovery.setPlaceholderText('https://diagnose.example.org'); field(root, 'Unabhängiger Diagnosezugang · eigene HTTPS-Adresse', self.recovery)
        self.open = QPushButton(tr('Diagnosezugang im Browser öffnen')); self.open.setAutoDefault(False); self.open.clicked.connect(self.open_recovery); root.addWidget(self.open, 0, Qt.AlignLeft)
        root.addWidget(text('Die Adresse und den Betreiberschlüssel erhältst Du bei der Servereinrichtung. Der Schlüssel gehört ausschließlich in die geschützte Diagnoseanmeldung.'))
        root.addWidget(text('Wenn der ganze Server nicht antwortet: Serveradresse, Internet und VPN prüfen. Als Betreiber Host oder VM über den getrennten Zugang prüfen. Ohne aktuellen Hostbefund bleiben Container und Datenbank unbekannt.'))
        root.addStretch()
        # The close action stays visible below the scrolling content, as in Panorama dialogs.
        footer = QHBoxLayout(); footer.addStretch(); outer.addLayout(footer)
        close = QPushButton(tr('Schließen')); close.setAutoDefault(False); close.clicked.connect(self.close); footer.addWidget(close)

    def run(self):
        if self.pending: return
        try: server = origin(self.server.text().strip())
        except SessionError:
            self.status.setText(tr('Bitte eine HTTPS-Serveradresse ohne Unterseite oder Anmeldedaten angeben.')); return
        request = QNetworkRequest(QUrl(server + '/api/status'))
        request.setTransferTimeout(3000)
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setAttribute(QNetworkRequest.CookieLoadControlAttribute, QNetworkRequest.Manual)
        request.setAttribute(QNetworkRequest.CookieSaveControlAttribute, QNetworkRequest.Manual)
        request.setRawHeader(b'Accept', b'application/json')
        if server == self.paired[0] and self.paired[1]:
            ssl = request.sslConfiguration()
            ssl.setCaCertificates(ssl.caCertificates() + QSslCertificate.fromPath(self.paired[1]))
            request.setSslConfiguration(ssl)
        self.pending = self.network.get(request); self.check.setEnabled(False); self.server.setEnabled(False)
        reply = self.pending; payload = bytearray()
        self.status.setText(tr('Öffentlicher Status wird geprüft …'))
        def receive():
            payload.extend(bytes(reply.readAll()))
            if len(payload) > 16384: reply.abort()
        reply.readyRead.connect(receive)
        def done():
            receive(); self.pending = None; self.check.setEnabled(True); self.server.setEnabled(True)
            try:
                if reply.error() != QNetworkReply.NoError or len(payload) > 16384: raise ValueError
                if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200: raise ValueError
                if reply.header(QNetworkRequest.ContentTypeHeader).split(';')[0] != 'application/json': raise ValueError
                value = json.loads(payload)
                if value.get('service') != 'Lumen Server' or type(value.get('ready')) is not bool: raise ValueError
                message = 'Der öffentliche Lumen-Status antwortet. Anmeldung, Datenbank und KI sind damit noch nicht geprüft.'
            except (ValueError, TypeError, AttributeError):
                message = 'Keine gültige Lumen-Antwort. Serveradresse, Verbindung und Zertifikat prüfen. Der Zustand von Containern und Datenbank bleibt offen.'
            self.status.setText(tr(message)); reply.deleteLater()
        reply.finished.connect(done)

    def open_recovery(self):
        try:
            target = origin(self.recovery.text().strip())
            try: server = origin(self.server.text().strip())
            except SessionError: server = None
            if target == server: raise SessionError('identity')
        except SessionError:
            self.status.setText(tr('Der Diagnosezugang braucht eine eigene HTTPS-Adresse, getrennt von der normalen Lumen-App.')); return
        if not QDesktopServices.openUrl(QUrl(target)):
            self.status.setText(tr('Der Browser konnte nicht geöffnet werden.'))

    def closeEvent(self, event):
        if self.pending: self.pending.abort()
        super().closeEvent(event)


def show_diagnostics(parent=None):
    dialog = DiagnosticsView(parent)
    # Keep the settings theme when embedded; the standalone app uses its existing palette.
    if parent is not None: dialog.setPalette(parent.palette())
    dialog.exec()
