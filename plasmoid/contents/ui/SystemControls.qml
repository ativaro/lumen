pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import org.kde.notificationmanager as Notifications

ColumnLayout {
    id: controls
    property var systemState: ({volume: null, muted: false, brightness: null, network: "Wird geladen …"})
    property bool busy: false
    property var settingsOverride: null
    readonly property var notificationSettings: settingsOverride || notifications
    signal control(string action, int value)
    spacing: 10
    Notifications.Settings { id: notifications; live: true }
    property date now: new Date()
    Timer { interval: 30000; running: controls.visible; repeat: true; onTriggered: controls.now = new Date() }

    Kirigami.Heading { text: "System"; level: 3; font.pixelSize: 19; font.weight: Font.DemiBold; color: Kirigami.Theme.textColor; Layout.bottomMargin: 8 }
    LumenButton {
        Layout.fillWidth: true; flat: true; text: "Hardware"; hint: "Temperatur · Lüfter · Leistung  ›"
        icon.name: "utilities-system-monitor"; onClicked: controls.control("hardware", 0)
    }
    LumenButton {
        Layout.fillWidth: true; implicitHeight: 50; flat: true; prominent: true
        icon.name: "network-wired"; symbolSize: 27
        text: "Netzwerk"; hint: controls.systemState.network
        onClicked: controls.control("network", 0)
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 18
        LumenIcon { name: "moon"; Layout.preferredWidth: 26; Layout.preferredHeight: 26; Layout.leftMargin: 12 }
        PC.Label { text: "Nicht stören"; font.pixelSize: 15; color: Kirigami.Theme.textColor; Layout.fillWidth: true }
        PC.Switch {
            id: dnd
            objectName: "doNotDisturb"
            Accessible.name: "Nicht stören für eine Stunde"
            PC.ToolTip.text: "Für eine Stunde"; PC.ToolTip.visible: hovered
            checked: controls.notificationSettings.notificationsInhibitedUntil > controls.now
            onClicked: {
                controls.notificationSettings.notificationsInhibitedUntil = checked ? new Date(Date.now() + 3600000) : new Date(0);
                controls.notificationSettings.save();
            }
            indicator: Rectangle {
                implicitWidth: 46; implicitHeight: 26; radius: 13
                y: (dnd.height - height) / 2
                color: dnd.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                border.width: dnd.visualFocus ? 2 : 0; border.color: Kirigami.Theme.textColor
                Rectangle { x: dnd.checked ? 23 : 3; y: 3; width: 20; height: 20; radius: 10; color: dnd.checked ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.backgroundColor; Behavior on x { NumberAnimation { duration: 120 } } }
            }
        }
    }
    PC.Label {
        visible: controls.notificationSettings.notificationsInhibitedByApplication
        Layout.fillWidth: true
        text: "Eine Anwendung unterdrückt zusätzlich Benachrichtigungen."
        wrapMode: Text.Wrap
    }
    Kirigami.Separator { Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        LumenButton { flat: true;
            objectName: "muteButton"
            implicitHeight: 32; topPadding: 4; bottomPadding: 4
            icon.name: controls.systemState.muted ? "audio-volume-muted" : "audio-volume-high"
            icon.color: Kirigami.Theme.textColor
            enabled: controls.systemState.volume !== null && !controls.busy
            Accessible.name: controls.systemState.muted ? "Ton einschalten" : "Stummschalten"
            onClicked: controls.control("mute", 0)
        }
        PC.Label { text: "Lautstärke"; font.pixelSize: 15; color: Kirigami.Theme.textColor; Layout.fillWidth: true }
        PC.Label { text: controls.systemState.volume === null ? "Nicht verfügbar" : controls.systemState.muted ? "Stumm" : controls.systemState.volume + " %" }
    }
    LumenSlider {
        id: volume
        objectName: "volumeSlider"
        Layout.fillWidth: true
        from: 0; to: 100; stepSize: 1
        enabled: controls.systemState.volume !== null && !controls.busy
        Accessible.name: "Lautstärke"
        property int requestedValue: 0
        onMoved: { requestedValue = Math.round(value); if (!pressed) controls.control("volume", requestedValue); }
        onPressedChanged: {
            if (pressed) requestedValue = Math.round(value);
            else if (enabled) controls.control("volume", requestedValue);
        }
        Binding { restoreMode: Binding.RestoreNone; target: volume; property: "value"; value: controls.systemState.volume || 0; when: !volume.pressed }
    }
    RowLayout {
        Layout.fillWidth: true
        LumenIcon { name: "brightness-high"; Layout.preferredWidth: 24; Layout.preferredHeight: 24; Layout.leftMargin: 12 }
        PC.Label { id: brightnessLabel; text: "Helligkeit"; font.pixelSize: 15; color: Kirigami.Theme.textColor; Layout.fillWidth: true }
        PC.Label { text: controls.systemState.brightness === null ? "Nicht verfügbar" : controls.systemState.brightness + " %" }
    }
    LumenSlider {
        id: brightness
        objectName: "brightnessSlider"
        Layout.fillWidth: true
        from: 1; to: 100; stepSize: 1
        enabled: controls.systemState.brightness !== null && !controls.busy
        Accessible.name: "Bildschirmhelligkeit"
        property int requestedValue: 0
        onMoved: { requestedValue = Math.round(value); if (!pressed) controls.control("brightness", requestedValue); }
        onPressedChanged: {
            if (pressed) requestedValue = Math.round(value);
            else if (enabled) controls.control("brightness", requestedValue);
        }
        Binding { restoreMode: Binding.RestoreNone; target: brightness; property: "value"; value: controls.systemState.brightness || 1; when: !brightness.pressed }
    }
    RowLayout {
        Layout.fillWidth: true
        LumenButton { Layout.fillWidth: true; implicitHeight: 32; flat: true; text: "Audiogeräte"; onClicked: controls.control("audio", 0) }
        LumenButton { Layout.fillWidth: true; implicitHeight: 32; flat: true; text: "Bildschirme"; onClicked: controls.control("display", 0) }
    }
    Item { Layout.fillHeight: true }
}
