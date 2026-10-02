pragma ComponentBehavior: Bound
import QtQuick
import org.kde.kirigami as Kirigami
import QtQuick.Layouts
import org.kde.plasma.components as PC

RowLayout {
    id: bar
    property string surface: "home"
    property var snapshot: ({active: [], attention: false, busy: false})
    property bool expanded: false
    signal toggle()
    signal launch(string action)
    signal search()
    signal voice()
    spacing: 12
    Layout.minimumHeight: 28
    Layout.preferredWidth: surface === "home" ? 266 : surface === "search" ? 460 : 62
    LumenButton {
        objectName: "homeButton"
        visible: bar.surface === "home" || bar.surface === "tasks"
        Layout.fillWidth: true
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        text: bar.surface === "home" ? "Lumen" : ""
        icon.name: "lumen"; symbolSize: 28
        font.pixelSize: 19; font.weight: Font.DemiBold
        flat: true; checkable: true; checked: bar.expanded
        Accessible.name: "Lumen Systemübersicht"
        onClicked: bar.toggle()
    }
    Rectangle { visible: bar.surface === "home"; color: Kirigami.Theme.disabledTextColor; opacity: 0.65; implicitWidth: 1; implicitHeight: 26 }
    LumenButton {
        visible: bar.surface === "home"
        objectName: "filesButton"
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        text: "Dateien"; icon.name: "folder"; font.pixelSize: 16
        flat: true; onClicked: bar.launch("files")
    }
    LumenButton {
        visible: bar.surface === "search"
        Layout.fillWidth: true
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        objectName: "searchButton"
        text: "Suchen oder fragen …"; icon.name: "search"
        font.pixelSize: 16
        flat: true
        Accessible.name: "Dateien und Apps suchen oder ein Gespräch führen"
        onClicked: bar.search()
    }
    LumenButton {
        visible: bar.surface === "search"
        objectName: "voiceButton"
        Layout.preferredWidth: 42
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        icon.name: "audio-input-microphone"
        flat: true
        Accessible.name: "Mit Lumen sprechen"
        PC.ToolTip.text: "Mit Lumen sprechen"
        PC.ToolTip.visible: hovered
        onClicked: bar.voice()
    }
    LumenButton {
        visible: bar.surface === "control"
        Layout.fillWidth: true
        Layout.fillHeight: true
        topPadding: 0; bottomPadding: 0
        objectName: "centerButton"
        icon.name: "adjustlevels"; symbolSize: 24
        flat: true; checkable: true; checked: bar.expanded
        Accessible.name: "Einstellungen, Systemsteuerung und Themes"
        onClicked: bar.toggle()
    }
}
