"""The collection and creation layouts share the approved Lumen design."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton
from lumen_i18n import tr
from tools_ui import button,label
from studio_design import surface,icon

ICONS={'app':'view-grid','routine':'view-calendar','tool':'tools-wizard','automation':'view-process-tree','code':'code-context'}
NAV={'routine':'Zeitpläne & Routinen','tool':'Werkzeuge','automation':'Automationen','code':'Code-Projekte'}

STYLE='''
QWidget#codeShell { background: palette(window); color: palette(text); }
QFrame#codeRail { background: palette(window); border-right: 1px solid palette(mid); }
QLabel#codeEyebrow { font-size: 10px; color: palette(placeholder-text); padding: 0 10px 12px; }
QLabel#codeTitle { font-size: 24px; font-weight: 500; padding: 2px 0; }
QLabel#codeSubtitle, QLabel#codeMuted { color: palette(placeholder-text); font-size: 12px; }
QLabel#codeError { color: palette(text); }
QLabel#codeFooter { color: palette(placeholder-text); border-top: 1px solid palette(mid); padding: 12px 20px; font-size: 10px; }
QPushButton#codeNav { text-align: left; background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 8px 12px; min-height: 20px; font-size: 14px; }
QPushButton#codeNav:hover, QPushButton#codeNav:checked { background: palette(midlight); border-color: transparent; color: palette(text); }
QPushButton#codeLink { border: 1px solid transparent; background: transparent; color: palette(link); text-align: left; padding: 7px 0; }
QPushButton#codeCard { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; text-align: left; min-height: 156px; padding: 0; }
QPushButton#codeCard:hover, QPushButton#codeCard:checked { border-color: palette(highlight); background: palette(alternate-base); }
QLabel#codeCardTitle { font-size: 18px; font-weight: 500; }
QPushButton#codeCard QLabel { background: transparent; border: none; }
QWidget#codeShell QLineEdit, QWidget#codeShell QPlainTextEdit, QWidget#codeShell QComboBox, QWidget#codeShell QSpinBox { background: palette(base); color: palette(text); border: 1px solid palette(mid); border-radius: 7px; padding: 10px 12px; }
QWidget#codeShell QTimeEdit, QWidget#codeShell QDateEdit { background: palette(base); color: palette(text); border: 1px solid palette(mid); border-radius: 7px; padding: 8px 10px; min-height: 22px; }
QWidget#codeShell QTabWidget::pane { border: none; }
QWidget#codeShell QTabBar::tab { min-width:0; background:transparent; padding:10px 14px; border:0; border-bottom:2px solid transparent; border-radius:0; }
QWidget#codeShell QTabBar::tab:selected { color:palette(text);border-bottom-color:palette(highlight); }
QWidget#codeShell QPlainTextEdit#codeSource { font-family: monospace; border: none; border-radius: 0; padding: 20px; }
QWidget#codeShell QScrollArea { background: transparent; border: none; }
QWidget#codeShell QScrollArea > QWidget > QWidget { background: palette(window); }
QWidget#codeShell QPushButton#toolButton:checked { background: palette(alternate-base); border: 1px solid palette(highlight); }
QWidget#codeShell QPushButton#toolButton { background: palette(base); border: 1px solid palette(mid); border-radius: 7px; padding: 9px 12px; }
QWidget#codeShell QPushButton#primary { background: palette(highlight); color: palette(highlighted-text); border: 1px solid palette(highlight); border-radius: 7px; padding: 9px 13px; }
QWidget#codeShell QPushButton:focus { border: 2px solid palette(highlight); }
QWidget#codeShell QPlainTextEdit#studioInput { background: transparent; border: none; padding: 0; }
QWidget#codeShell QWidget#studioChat QPushButton#primary { padding: 0; min-height: 0; font-size: 23px; }
QWidget#codeShell QTabBar#studioResultTabs::tab { margin-right: 15px; font-size: 11px; }
QFrame#codeLogic { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
QFrame#codeLogic QLabel { background: transparent; border: none; }
QLabel#codeLogicWord { color: palette(link); font-size: 24px; font-weight: 500; }
QPushButton#codeFold { text-align: left; background: palette(base); border: 1px solid palette(mid); border-radius: 8px; padding: 12px 16px; min-height: 24px; }
QLabel#codeJoin { color: palette(link); padding: 3px 20px; font-size: 19px; }
QListWidget#codeSteps { background: palette(base); border: 1px solid palette(mid); border-radius: 7px; }
QListWidget#codeSteps::item { padding: 9px 12px; }
QListWidget#codeSteps::item:selected { background: palette(alternate-base); color: palette(link); }
QTextBrowser#codeReview { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; padding: 21px; }
QListWidget#codeCategories { background: transparent; border: none; outline: none; }
QListWidget#codeCategories::item { padding: 11px 9px; border: 1px solid transparent; border-radius: 7px; margin-bottom: 3px; }
QListWidget#codeCategories::item:selected { background: palette(midlight); color: palette(text); border-color: transparent; }
QTreeWidget#codeEntries { background: palette(base); alternate-background-color: palette(base); border: 1px solid palette(mid); border-radius: 10px; padding: 8px; outline: none; }
QTreeWidget#codeEntries::item { padding: 12px 10px; border-bottom: 1px solid palette(mid); }
QTreeWidget#codeEntries::item:selected { background: palette(alternate-base); color: palette(text); }
QTreeWidget#codeEntries QHeaderView::section { background: palette(base); color: palette(placeholder-text); border: none; padding: 10px; font-size: 11px; }
'''


def shell(owner):
    owner.setObjectName('codeShell');surface(owner)
    owner.setStyleSheet(Path(__file__).with_name('studio.qss').read_text()+'\n'+STYLE)
    root=QVBoxLayout(owner);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
    from desktop_design import AppHeader, PAGE_MARGIN, NAV_WIDTH
    chrome=QWidget();top=QVBoxLayout(chrome);top.setContentsMargins(PAGE_MARGIN,20,PAGE_MARGIN,0)
    header=AppHeader(tr('Lumen Code & Automation'),tr('Werkzeuge, Routinen, Automationen und Code-Projekte.'))
    top.addWidget(header);root.addWidget(chrome)
    body=QHBoxLayout();body.setContentsMargins(0,0,0,0);body.setSpacing(0);root.addLayout(body,1)
    rail=QFrame();rail.setObjectName('codeRail');rail.setFixedWidth(NAV_WIDTH)
    nav=QVBoxLayout(rail);nav.setContentsMargins(16,24,16,20);nav.setSpacing(8)
    nav.addWidget(label(tr('MEINE SAMMLUNG'),'codeEyebrow'));body.addWidget(rail)
    main=QWidget();body.addWidget(main,1)
    footer=label(tr('Meine Sammlung'),'codeFooter');root.addWidget(footer)
    return main,nav,footer


def editor_shell(owner,title,subtitle):
    """A dedicated task view; collection navigation belongs to the collection."""
    from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
    owner.setObjectName('codeShell');surface(owner);owner.setStyleSheet(STYLE)
    root=QVBoxLayout(owner);root.setContentsMargins(PAGE_MARGIN,20,PAGE_MARGIN,20);root.setSpacing(PAGE_SPACING)
    header=AppHeader(title,subtitle);root.addWidget(header)
    main=QWidget();root.addWidget(main,1)
    footer=label('','codeMuted');root.addWidget(footer)
    return main,header,footer


def navigation(layout,collection,select,existing_apps=False):
    all_entries=button(tr('Alle Einträge'),collection,'view-list-details');all_entries.setObjectName('codeNav');layout.addWidget(all_entries)
    layout.addSpacing(18);controls={}
    for key,title in {**NAV,**({'app':'Vorhandene kleine Apps'} if existing_apps else {})}.items():
        control=button(tr(title).replace('&','&&'),lambda _=False,k=key:select(k),ICONS[key]);control.setCheckable(True);control.setObjectName('codeNav');layout.addWidget(control);controls[key]=control
    layout.addStretch();layout.addWidget(label(tr('Deine Idee.\nDein nächster Helfer.'),'codeMuted'))
    return controls


def card(title,description,example,callback,kind):
    control=QPushButton();control.setObjectName('codeCard');control.setCursor(Qt.PointingHandCursor)
    control.setAccessibleName(title);control.setAccessibleDescription(description);control.clicked.connect(callback)
    box=QVBoxLayout(control);box.setContentsMargins(20,18,20,18);box.setSpacing(12)
    heading=QHBoxLayout();mark=QLabel();mark.setPixmap(icon(ICONS[kind]).pixmap(20,20));heading.addWidget(mark);heading.addWidget(label(title,'codeCardTitle'),1);heading.addWidget(label('↗','codeMuted'));box.addLayout(heading)
    box.addWidget(label(description));box.addStretch();box.addWidget(label(example,'codeMuted'))
    for child in control.findChildren(QLabel):child.setAttribute(Qt.WA_TransparentForMouseEvents)
    control.setMinimumHeight(156)
    return control


def logic(box,word,description):
    frame=QFrame();frame.setObjectName('codeLogic');inside=QVBoxLayout(frame);inside.setContentsMargins(18,16,18,18);inside.setSpacing(12)
    head=QHBoxLayout();head.addWidget(label(tr(word),'codeLogicWord'));head.addWidget(label(tr(description),'codeMuted'),1);inside.addLayout(head);box.addWidget(frame)
    return inside
