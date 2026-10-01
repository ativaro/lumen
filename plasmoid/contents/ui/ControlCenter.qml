pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

Item {
    id: center
    property var systemState: ({volume: null, muted: false, brightness: null, network: "Wird geladen …"})
    property string error: ""
    property bool busy: false
    property var notificationSettings: null
    signal launch(string action)
    signal refresh()
    signal control(string action, int value)
    ColumnLayout {
    anchors.fill: parent; anchors.margins: 18
    spacing: 18
    RowLayout {
        Layout.fillWidth: true
        Kirigami.Heading { text: "Einstellungen"; level: 2; font.pixelSize: 26; font.weight: Font.DemiBold; Layout.fillWidth: true }
        LumenButton { flat: true;
            icon.name: "view-refresh"; icon.color: Kirigami.Theme.textColor
            Accessible.name: "Aktualisieren"; onClicked: center.refresh()
        }
    }
    PC.Label {
        visible: center.error !== ""; text: center.error; textFormat: Text.PlainText
        color: Kirigami.Theme.negativeTextColor; wrapMode: Text.Wrap; Layout.fillWidth: true
    }
    SystemControls {
        Layout.fillWidth: true; Layout.fillHeight: true
        systemState: center.systemState; busy: center.busy; settingsOverride: center.notificationSettings
        onControl: (action, value) => center.control(action, value)
    }
    Kirigami.Separator { Layout.fillWidth: true }
    LumenButton { flat: true; Layout.fillWidth: true; text: "Lumen & Files"; hint: "Einstellungen  ›"; icon.name: "configure"; objectName: "preferencesButton"; onClicked: center.launch("settings") }
    RowLayout {
        Layout.fillWidth: true
        LumenButton { flat: true; Layout.fillWidth: true; text: "Themes"; icon.name: "preferences-desktop-theme"; objectName: "themesButton"; onClicked: center.control("appearance", 0) }
        LumenButton { flat: true; Layout.fillWidth: true; text: "System"; icon.name: "computer"; Accessible.name: "Systemeinstellungen"; onClicked: center.control("desktop-settings", 0) }
        LumenButton { flat: true; icon.name: "system-lock-screen"; objectName: "lockButton"; Accessible.name: "Bildschirm sperren"; onClicked: center.control("lock", 0) }
    }
}
}
