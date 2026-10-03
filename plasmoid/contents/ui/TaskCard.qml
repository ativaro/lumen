import "Translations.js" as I18n
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: card
    property string uiLanguage: Qt.locale().name.toLowerCase().indexOf("de") === 0 ? "de" : "en"
    function tr(source, args) { return I18n.tr(source, uiLanguage, args); }
    required property var task
    property bool expanded: false
    property bool dismissBusy: false
    signal toggle()
    signal openTask(string taskId)
    signal dismissTask(string taskId)
    spacing: Kirigami.Units.smallSpacing

    RowLayout {
    Layout.fillWidth: true
    PC.ItemDelegate {
        id: toggleButton
        objectName: "taskToggle-" + card.task.id
        Layout.fillWidth: true
        Accessible.name: card.task.title + ", " + card.task.state
        Accessible.description: card.expanded ? card.tr("Ergebnis einklappen") : card.tr("Ergebnis anzeigen")
        onClicked: card.toggle()
        Keys.onReturnPressed: card.toggle()
        Keys.onEnterPressed: card.toggle()
        implicitHeight: 80
        background: Rectangle { radius: 10; color: toggleButton.hovered || toggleButton.down ? Kirigami.Theme.alternateBackgroundColor : "transparent"; border.width: toggleButton.visualFocus ? 2 : 0; border.color: Kirigami.Theme.highlightColor }
        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing * 2
            Rectangle {
                Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: 18
                color: card.task.status === "completed" ? Kirigami.Theme.alternateBackgroundColor : Kirigami.Theme.alternateBackgroundColor
                LumenIcon {
                    anchors.centerIn: parent; width: 22; height: 22
                    color: card.task.status === "completed" ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
                    name: card.task.status === "completed" ? "check" : card.task.status === "failed" ? "dialog-error"
                        : card.task.status === "needs_input" ? "dialog-question" : "view-task"
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                PC.Label {
                    Layout.fillWidth: true
                    text: card.task.title
                    font.pixelSize: 15
                    color: Kirigami.Theme.textColor
                    textFormat: Text.PlainText
                    maximumLineCount: 2
                    wrapMode: Text.Wrap
                    elide: Text.ElideRight
                }
                PC.Label {
                    Layout.fillWidth: true
                    text: card.task.state + (card.task.total > 0 ? " · " + card.tr("{0} von {1} Schritten", [card.task.cursor, card.task.total]) : "")
                    textFormat: Text.PlainText
                    font: Kirigami.Theme.smallFont
                    color: Kirigami.Theme.disabledTextColor
                    wrapMode: Text.Wrap
                }
            }
            LumenIcon {
                color: Kirigami.Theme.disabledTextColor
                name: card.expanded ? "arrow-up" : "arrow-down"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
        }
    }
    LumenButton {
        objectName: "taskClose-" + card.task.id
        visible: card.task.status === "completed" || card.task.status === "cancelled"
        enabled: !card.dismissBusy
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: 18
        flat: true; icon.name: "window-close"; symbolSize: 18
        Accessible.name: card.tr("Aufgabe aus der Übersicht entfernen: ") + card.task.title
        PC.ToolTip.text: card.tr("Aus der Übersicht entfernen · Verlauf behalten")
        PC.ToolTip.visible: hovered
        onClicked: card.dismissTask(card.task.id)
    }
    }
    PC.ProgressBar {
        Layout.fillWidth: true
        visible: card.task.status === "running"
        indeterminate: card.task.total === 0
        from: 0
        to: Math.max(1, card.task.total)
        value: card.task.cursor
        Accessible.name: card.tr("Fortschritt: ") + card.task.title
    }
    ColumnLayout {
        visible: card.expanded
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing * 2
        Layout.rightMargin: Kirigami.Units.smallSpacing * 2
        spacing: Kirigami.Units.smallSpacing * 2
        PC.Label {
            objectName: "taskResult-" + card.task.id
            Layout.fillWidth: true
            text: card.task.error || card.task.result || (card.task.status === "needs_input"
                ? card.tr("Dieser Auftrag braucht deine Eingabe in Lumen.") : card.tr("Noch kein Ergebnis vorhanden."))
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
        }
        PC.Label {
            Layout.fillWidth: true
            visible: !!card.task.truncated
            text: card.tr("Auszug · Vollständiges Ergebnis im Auftrag")
            font: Kirigami.Theme.smallFont
            color: Kirigami.Theme.disabledTextColor
            wrapMode: Text.Wrap
        }
        LumenButton {
            text: card.tr("Auftrag öffnen")
            icon.name: "document-open"
            icon.color: Kirigami.Theme.textColor
            onClicked: card.openTask(card.task.id)
        }
    }
}
