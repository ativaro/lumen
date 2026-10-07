pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property var controller
    readonly property var theme: controller.theme
    signal showTasks()
    spacing: 30
    GridLayout {
        Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 12; Layout.bottomMargin: 12
        columns: root.width < 700 ? 3 : 6; columnSpacing: root.width < 700 ? 22 : 32; rowSpacing: 12
        Repeater { model: root.controller.homeView.apps
            ColumnLayout {
                id: appEntry
                required property var modelData
                spacing: 8
                Button { id: appButton; objectName: "homeApp_"+appEntry.modelData.id; Layout.preferredWidth: root.width < 700 ? 85 : 100; Layout.preferredHeight: 84; Accessible.name: appEntry.modelData.title; onClicked: root.controller.homeView.launch_app(appEntry.modelData.id)
                    background: Rectangle { color: appButton.hovered ? root.theme.hover : Qt.alpha(root.theme.base,0.45); border.color: appButton.activeFocus ? root.theme.accent : Qt.alpha(root.theme.border,0.5); radius: 16 }
                    contentItem: Image { source: "image://icons/"+appEntry.modelData.icon+"?"+root.theme.name+(appEntry.modelData.id === "apps" ? "&tint="+encodeURIComponent(root.theme.accent) : ""); sourceSize: Qt.size(40,40); fillMode: Image.Pad }
                }
                Label { Layout.alignment: Qt.AlignHCenter; text: appEntry.modelData.title; textFormat: Text.PlainText; color: root.theme.text; font.pixelSize: root.theme.fontSize-1 }
            }
        }
    }
    GridLayout {
        Layout.fillWidth: true; columns: root.width > 850 ? 2 : 1; columnSpacing: 32; rowSpacing: 24
        HomeList { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 520; controller: root.controller; kind: "tasks"; onShowAll: root.showTasks() }
        HomeList { id: recent; Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 410; controller: root.controller; kind: "recent"; onShowAll: limit = 20 }
    }
}
