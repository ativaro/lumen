pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import "Translations.js" as I18n

Item {
    id: detail
    property var notice: null
    property string uiLanguage: "de"
    property bool backVisible: false
    property date now: new Date()
    signal action(string identity, bool system, string operation)
    signal back()
    function tr(text) { return I18n.tr(text, uiLanguage); }
    function act(operation) { if(notice) action(notice.id,!!notice.system,operation); }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 16
        RowLayout {
            Layout.fillWidth: true
            LumenButton { visible: detail.backVisible; objectName: "notificationBack"; flat: true; icon.name: "go-previous"; text: detail.tr("Zurück"); onClicked: detail.back() }
            PC.Label { text: detail.notice ? detail.notice.source : ""; textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; color: Kirigami.Theme.disabledTextColor }
            LumenButton { flat: true; icon.name: "view-more-symbolic"; Accessible.name: detail.tr("Weitere Aktionen"); onClicked: more.popup() }
            QQC2.Menu {
                id: more
                QQC2.MenuItem { visible: !!detail.notice && !detail.notice.system; text: detail.tr(detail.notice && detail.notice.read ? "Als ungelesen" : "Gelesen"); onTriggered: detail.act(detail.notice.read ? "unread" : "read") }
                QQC2.MenuItem { visible: !!detail.notice && !detail.notice.system && !detail.notice.archived; text: detail.tr(detail.notice && detail.notice.snoozed*1000>detail.now.getTime() ? "Jetzt" : "In einer Stunde"); onTriggered: detail.act(detail.notice.snoozed*1000>detail.now.getTime() ? "now" : "later") }
                QQC2.MenuItem { visible: !!detail.notice && !detail.notice.system && !!detail.notice.completion_supported && detail.notice.kind!=="decision" && !detail.notice.archived; text: detail.tr(detail.notice && detail.notice.resolved ? "Wieder öffnen" : "Erledigen"); onTriggered: detail.act(detail.notice.resolved ? "reopen" : "resolve") }
                QQC2.MenuItem { text: detail.tr(detail.notice && detail.notice.archived ? "Wiederherstellen" : "Meldung schließen"); onTriggered: detail.act(detail.notice.archived ? "restore" : "archive") }
            }
        }
        PC.Label { text: detail.notice ? Qt.formatDateTime(new Date(detail.notice.updated*1000),"dd.MM.yyyy · hh:mm") : ""; color: Kirigami.Theme.disabledTextColor; font.pixelSize: 12 }
        PC.Label { text: detail.notice ? detail.notice.title : ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; font.pixelSize: 24; font.weight: Font.Medium; Layout.fillWidth: true }
        QQC2.ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            QQC2.TextArea {
                text: detail.notice ? detail.notice.body : ""; readOnly: true; selectByMouse: true
                textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; background: null
                padding: 0; color: Kirigami.Theme.textColor; font.pixelSize: 15
                Accessible.name: detail.tr("Inhalt der Benachrichtigung")
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.alpha(Kirigami.Theme.textColor,0.14) }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: detail.notice ? detail.notice.actions || [] : []
                delegate: LumenButton {
                    required property var modelData
                    text: modelData.label; prominent: true
                    onClicked: detail.act(modelData.key)
                }
            }
            LumenButton {
                objectName: "notificationDiscuss"; text: detail.tr("Mit Lumen besprechen"); icon.name: "lumen"
                PC.ToolTip.text: detail.tr("Öffnet einen Entwurf mit dieser Meldung. Erst Senden übermittelt ihn an deinen KI-Anbieter.")
                PC.ToolTip.visible: hovered
                onClicked: detail.act("discuss")
            }
        }
    }
}
