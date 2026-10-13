pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property var controller
    readonly property var theme: controller.theme
    signal showTasks()
    spacing: 34
    RowLayout {
        Layout.alignment: Qt.AlignHCenter
        spacing: 8
        LumenButton {
            id: translateText; objectName: "translateText"; theme: root.theme; quiet: true
            icon.name: "document-edit"; icon.width: 15; icon.height: 15
            font.pixelSize: Math.max(12, root.theme.fontSize-5); implicitHeight: 36
            background: Rectangle { radius: 8; color: translateText.hovered || translateText.down ? root.theme.hover : Qt.alpha(root.theme.base,0.65); border.color: translateText.activeFocus ? root.theme.accent : "transparent" }
            text: root.controller.text("Text überarbeiten"); onClicked: root.controller.homeView.launch_app("translate")
        }
        LumenButton { theme: root.theme; quiet: true; icon.name: "notifications"; icon.width: 15; icon.height: 15; font.pixelSize: Math.max(12, root.theme.fontSize-5); implicitHeight: 36; text: root.controller.text("Meldungen"); onClicked: root.controller.homeView.launch_app("notification") }
    }
    GridLayout {
        Layout.fillWidth: true; columns: root.width > 680 ? 2 : 1; columnSpacing: 34; rowSpacing: 28
        HomeList { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 520; controller: root.controller; kind: "sessions"; limit: 5; onShowAll: limit += 5 }
        HomeList { id: recent; Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 445; controller: root.controller; kind: "recent"; limit: 4; onShowAll: limit = 20 }
    }
}
