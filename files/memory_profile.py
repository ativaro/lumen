"""A readable view over existing global memories, without a second profile store."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton
from lumen_i18n import tr
from settings_navigation import label
from notes_query import timestamp_text


class MemoryProfile(QScrollArea):
    noteRequested = Signal(str)

    def __init__(self, controls, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QScrollArea.NoFrame)
        body=QWidget(); self.setWidget(body)
        root=QVBoxLayout(body); root.setContentsMargins(28,22,28,18); root.setSpacing(14)
        root.addWidget(label(tr('Über dich'),'heading'))
        root.addWidget(label(tr('Was du Lumen über deine Vorlieben und Arbeitsweise mitgeteilt hast. Öffne einen Eintrag, um ihn zu korrigieren oder vergessen zu lassen.'),'muted'))
        root.addWidget(controls)
        self.entries=QVBoxLayout(); self.entries.setSpacing(10); root.addLayout(self.entries)
        root.addStretch()
        self.snapshot=None

    def update_notes(self, notes):
        notes=[n for n in notes if not n.get('memory',{}).get('scope') and n.get('memory',{}).get('kind','fact') in ('preference','fact','decision')]
        snapshot=[(n['path'],n['hash'],n.get('memory',{})) for n in notes]
        if snapshot==self.snapshot:return
        self.snapshot=snapshot
        while self.entries.count():
            item=self.entries.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        if not notes:
            self.entries.addWidget(label(tr('Noch kein Nutzerprofil. Teile Lumen mit, was dir wichtig ist. Bei aktiviertem Lernen entscheidet das Modell, welche Aussagen dauerhaft hilfreich sind.'),'muted'))
        for kind,title in [('preference',tr('Vorlieben & Arbeitsweise')),('fact',tr('Von dir mitgeteilte Fakten')),('decision',tr('Deine Entscheidungen'))]:
            group=sorted((n for n in notes if n.get('memory',{}).get('kind','fact')==kind),key=lambda n:n.get('memory',{}).get('updated',0),reverse=True)
            if not group:continue
            self.entries.addWidget(label(title,'settingsSectionTitle'))
            for note in group:
                entry=QPushButton();entry.setAutoDefault(False);entry.setObjectName('memoryProfileEntry')
                entry.setAccessibleName(note['title']);entry.clicked.connect(lambda checked=False,path=note['path']:self.noteRequested.emit(path))
                content=QVBoxLayout(entry);content.setContentsMargins(12,10,12,10)
                heading=label(note['title'],'settingsSectionTitle')
                lines=note['text'].splitlines()
                if lines and lines[0].startswith('# '):lines=lines[1:]
                description=label(' '.join(lines).strip()[:260],'muted')
                for child in (heading,description):child.setAttribute(Qt.WA_TransparentForMouseEvents);content.addWidget(child)
                when=timestamp_text(note)
                if when:
                    caption=label(when,'muted');caption.setAttribute(Qt.WA_TransparentForMouseEvents);content.addWidget(caption)
                if note.get('memory',{}).get('correction'):
                    caption=label(tr('Nach deiner Korrektur aktualisiert'),'muted');caption.setAttribute(Qt.WA_TransparentForMouseEvents);content.addWidget(caption)
                if note.get('memory',{}).get('sync_conflict') or not note.get('memory',{}).get('allowed',True):
                    caption=label(tr('Konflikt prüfen · nicht als Kontext verwendet') if note['memory'].get('sync_conflict') else tr('Noch nicht für Lumen freigegeben'),'muted')
                    caption.setAttribute(Qt.WA_TransparentForMouseEvents);content.addWidget(caption)
                self.entries.addWidget(entry)
