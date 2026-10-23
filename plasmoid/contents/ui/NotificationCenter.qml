pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import "Translations.js" as I18n

Item {
    id: center
    property string uiLanguage: "de"
    function tr(source) { return I18n.tr(source, uiLanguage); }
    property var items: []
    property bool full: false
    property bool inhibited: false
    property bool gaming: false
    property string error: ""
    property int pageSize: 30
    property string filter: "all"
    property bool grouped: false
    property date now: new Date()
    signal action(string identity, bool system, string operation)
    signal toggleDnd()
    signal showAll()
    signal preferences()
    readonly property var filtered: items.filter(function(row) {
        const matches = !search.text || (row.title+" "+row.body+" "+row.source).toLowerCase().indexOf(search.text.toLowerCase())>=0;
        const later = row.snoozed*1000 > center.now.getTime();
        return matches && (center.filter==="history" ? row.archived : !row.archived &&
            (center.filter==="done" ? !!row.resolved : !row.resolved && (center.filter==="later" ? later : !later && (center.filter!=="attention" || row.attention || ["question","decision","problem"].indexOf(row.kind)>=0))));
    }).sort((a,b)=>center.grouped ? a.source.localeCompare(b.source) || b.updated-a.updated : b.updated-a.updated)
    Timer { interval: 30000; running: center.visible; repeat: true; onTriggered: center.now = new Date() }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: center.full ? 28 : 18; spacing: 14
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true; spacing: 4
                Kirigami.Heading { text: "Lumen Notification"; level: 2; font.pixelSize: 24; font.weight: Font.DemiBold }
                PC.Label { text: center.tr("Alles Wichtige an einem Ort"); color: Kirigami.Theme.disabledTextColor; font.pixelSize: 13 }
            }
            LumenButton {
                objectName: "notificationDnd"; flat: true; checkable: true; checked: center.inhibited
                icon.name: center.inhibited ? "notifications-disabled" : "notifications"
                Accessible.name: center.tr("Nicht stören"); onClicked: center.toggleDnd()
                PC.ToolTip.text: center.tr("Nicht stören"); PC.ToolTip.visible: hovered
            }
            LumenButton { flat: true; icon.name: "configure"; Accessible.name: center.tr("Benachrichtigungen einstellen"); onClicked: center.preferences() }
            LumenButton {
                objectName: "notificationGroup"; flat: true; checkable: true; checked: center.grouped
                icon.name: "view-list-tree"; Accessible.name: center.tr("Nach App gruppieren")
                PC.ToolTip.text: center.tr("Nach App gruppieren"); PC.ToolTip.visible: hovered
                onClicked: center.grouped=!center.grouped
            }
        }
        PC.TextField {
            id: search; objectName: "notificationSearch"; Layout.fillWidth: true
            placeholderText: center.tr("Meldungen durchsuchen …"); Accessible.name: placeholderText
            onTextChanged: center.pageSize=30
        }
        Flow {
            Layout.fillWidth: true; spacing: 4
            Repeater {
                model: [{key:"all",label:"Offen"},{key:"attention",label:"Braucht dich"},{key:"later",label:"Später"},{key:"done",label:"Erledigt"},{key:"history",label:"Verlauf"}]
                delegate: LumenButton {
                    required property var modelData
                    flat: true; text: center.tr(modelData.label)
                    checkable: true; checked: center.filter===modelData.key
                    onClicked: { center.filter=modelData.key; center.pageSize=30; }
                }
            }
        }
        PC.Label { visible: center.error!==""; text: center.error; textFormat: Text.PlainText; wrapMode: Text.Wrap; Layout.fillWidth: true; color: Kirigami.Theme.negativeTextColor }
        ListView {
            id: list; objectName: "notificationList"; Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; spacing: 0; reuseItems: true
            model: center.filtered.slice(0, center.pageSize)
            PC.ScrollBar.vertical: PC.ScrollBar {}
            delegate: Rectangle {
                id: card
                required property var modelData
                width: list.width; height: content.implicitHeight+48; color: "transparent"
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Qt.alpha(Kirigami.Theme.textColor,0.14) }
                ColumnLayout {
                    id: content; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; anchors.topMargin: 24; spacing: 12
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Kirigami.Icon { source: card.modelData.icon || "notifications"; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                        PC.Label { text: card.modelData.source + (({result:"Ergebnis",question:"Rückfrage",decision:"Entscheidung",suggestion:"Vorschlag",problem:"Problem",reminder:"Erinnerung"})[card.modelData.kind] ? " · "+center.tr(({result:"Ergebnis",question:"Rückfrage",decision:"Entscheidung",suggestion:"Vorschlag",problem:"Problem",reminder:"Erinnerung"})[card.modelData.kind]) : ""); textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: Kirigami.Theme.disabledTextColor; font.pixelSize: 12 }
                        PC.Label { text: Qt.formatDateTime(new Date(card.modelData.updated*1000), "dd.MM. hh:mm"); color: Kirigami.Theme.disabledTextColor; font.pixelSize: 12 }
                        Rectangle { visible: !card.modelData.read; implicitWidth: 6; implicitHeight: 6; radius: 3; color: Kirigami.Theme.highlightColor; Accessible.name: center.tr("Ungelesen") }
                        LumenButton {
                            flat: true; implicitHeight: 28; symbolSize: 16; topPadding: 3; bottomPadding: 3
                            icon.name: card.modelData.archived ? "edit-undo" : "window-close"
                            Accessible.name: center.tr(card.modelData.archived ? "Wiederherstellen" : "Meldung schließen")
                            onClicked: center.action(card.modelData.id, card.modelData.system, card.modelData.archived ? "restore" : "archive")
                        }
                    }
                    PC.Label { text: card.modelData.title; textFormat: Text.PlainText; font.pixelSize: 16; font.weight: Font.DemiBold; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    PC.Label { visible: text!==""; text: card.modelData.body; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: center.full ? 12 : 4; elide: Text.ElideRight; Layout.fillWidth: true; font.pixelSize: 14 }
                    Flow {
                        Layout.fillWidth: true; spacing: 6
                        Repeater {
                            model: card.modelData.actions || []
                            delegate: LumenButton {
                                required property var modelData
                                text: modelData.label; prominent: true; implicitHeight: 44
                                onClicked: center.action(card.modelData.id, card.modelData.system, modelData.key)
                            }
                        }
                        LumenButton {
                            objectName: "notificationDiscuss"; text: center.tr("Mit Lumen besprechen"); implicitHeight: 44
                            icon.name: "lumen"
                            PC.ToolTip.text: center.tr("Öffnet einen Entwurf mit dieser Meldung. Erst Senden übermittelt ihn an deinen KI-Anbieter.")
                            PC.ToolTip.visible: hovered
                            onClicked: center.action(card.modelData.id, card.modelData.system, "discuss")
                        }
                        LumenButton { visible: !card.modelData.system && card.modelData.completion_supported && card.modelData.kind!=="decision" && !card.modelData.archived; flat: true; text: center.tr(card.modelData.resolved ? "Wieder öffnen" : "Erledigen"); implicitHeight: 44; onClicked: center.action(card.modelData.id, false, card.modelData.resolved ? "reopen" : "resolve") }
                        LumenButton { visible: !card.modelData.system; flat: true; text: center.tr(card.modelData.read ? "Als ungelesen" : "Gelesen"); implicitHeight: 44; onClicked: center.action(card.modelData.id, false, card.modelData.read ? "unread" : "read") }
                        LumenButton { visible: !card.modelData.system && !card.modelData.archived; flat: true; text: center.tr(card.modelData.snoozed*1000>center.now.getTime() ? "Jetzt" : "In einer Stunde"); implicitHeight: 44; onClicked: center.action(card.modelData.id, false, card.modelData.snoozed*1000>center.now.getTime() ? "now" : "later") }
                    }
                }
            }
            footer: LumenButton { visible: center.filtered.length>center.pageSize; text: center.tr("Weitere laden"); onClicked: center.pageSize+=30 }
            ColumnLayout {
                anchors.centerIn: parent; visible: list.count===0; spacing: 12; width: parent.width-40
                Kirigami.Icon { source: "notifications"; Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 40; Layout.preferredHeight: 40; opacity: 0.5 }
                PC.Label { text: center.tr("Hier ist gerade alles ruhig."); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; font.pixelSize: 18 }
                PC.Label { text: center.tr("Neue Meldungen erscheinen automatisch."); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: Kirigami.Theme.disabledTextColor }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            PC.Label { text: center.tr(center.gaming ? "Spiel erkannt · Meldungen werden still gesammelt." : "Systemmeldungen bleiben auf diesem Gerät."); Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor }
            LumenButton { visible: !center.full; flat: true; text: center.tr("Alle anzeigen"); icon.name: "view-fullscreen"; onClicked: center.showAll() }
        }
    }
}
