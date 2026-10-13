pragma ComponentBehavior: Bound
import "Translations.js" as I18n
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: panel
    property string uiLanguage: Qt.locale().name.toLowerCase().indexOf("de") === 0 ? "de" : "en"
    function tr(source, args) { return I18n.tr(source, uiLanguage, args); }
    property var snapshot: ({active: [], recent: [], error: "", busy: false, attention: false})
    property string title: "Lumen"
    signal openApp(string appId)
    signal launch(string action)
    signal refresh()
    spacing: Kirigami.Units.smallSpacing * 2

    RowLayout {
        Layout.fillWidth: true
        Kirigami.Heading { text: panel.title; font.pixelSize: 24; font.weight: Font.DemiBold; level: 2; Layout.fillWidth: true }
        LumenButton { flat: true;
            icon.name: "view-refresh"
            icon.color: Kirigami.Theme.textColor
            text: panel.tr("Aktualisieren")
            display: PC.AbstractButton.IconOnly
            Accessible.name: text
            PC.ToolTip.text: text
            PC.ToolTip.visible: hovered
            onClicked: panel.refresh()
        }
    }
    GridLayout {
        id: appGrid
        objectName: "appGrid"
        Layout.fillWidth: true
        columns: panel.width >= 440 ? 5 : 4
        columnSpacing: 4; rowSpacing: 4
        Repeater {
            model: panel.snapshot.apps || []
            PC.Button {
                id: appButton
                required property var modelData
                Kirigami.Theme.inherit: true
                objectName: "app-" + modelData.id
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                Layout.preferredHeight: 84
                hoverEnabled: true
                activeFocusOnTab: true
                Accessible.name: modelData.title
                PC.ToolTip.text: modelData.title + " · " + modelData.description
                PC.ToolTip.visible: hovered
                PC.ToolTip.delay: 700
                background: Rectangle {
                    radius: 12
                    color: appButton.down ? Qt.alpha(Kirigami.Theme.highlightColor, 0.20)
                        : appButton.hovered || appButton.visualFocus ? Kirigami.Theme.alternateBackgroundColor : "transparent"
                    border.width: appButton.visualFocus ? 2 : 0
                    border.color: Kirigami.Theme.highlightColor
                }
                contentItem: ColumnLayout {
                    spacing: 4
                    LumenIcon {
                        name: appButton.modelData.id === "lumen" ? "lumen" : "lumen-" + appButton.modelData.id
                        color: panel.Kirigami.Theme.textColor
                        Layout.alignment: Qt.AlignHCenter
                        objectName: "appIcon-" + appButton.modelData.id
                        Layout.preferredWidth: 40; Layout.preferredHeight: 40
                    }
                    PC.Label {
                        text: appButton.modelData.label
                        color: panel.Kirigami.Theme.textColor
                        textFormat: Text.PlainText
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
                onClicked: panel.openApp(modelData.id)
            }
        }
    }
    Kirigami.Separator { Layout.fillWidth: true }
    LumenButton {
        Layout.fillWidth: true
        flat: true
        objectName: "allTasksButton"
        text: panel.tr("Alle Aufgaben")
        hint: "›"
        icon.name: "view-task"
        icon.color: Kirigami.Theme.textColor
        onClicked: panel.launch("tasks")
    }
}
