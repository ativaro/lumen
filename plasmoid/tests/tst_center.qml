import QtQuick
import QtTest
import org.kde.kirigami as Kirigami
import "../contents/ui" as Lumen

Rectangle {
    id: scene
    width: 540; height: 640
    color: "#212b2f"
    QtObject {
        id: settings
        property date notificationsInhibitedUntil: new Date(0)
        property bool notificationsInhibitedByApplication: false
        property int saves: 0
        function save() { saves++; }
    }
    Lumen.ControlCenter {
        id: center
        anchors.fill: parent; anchors.margins: 16
        notificationSettings: settings
        systemState: ({volume: 55, muted: false, brightness: 80, network: "Verbunden"})
    }
    SignalSpy { id: action; target: center; signalName: "control" }
    SignalSpy { id: launch; target: center; signalName: "launch" }
    TestCase {
        name: "LumenControlCenter"
        when: windowShown
        function test_hardware_pointer_reaches_center() {
            action.clear();
            const system = findChild(center, "lumenSystemButton");
            verify(system !== null);
            mouseClick(system, system.width / 2, system.height / 2);
            compare(action.count, 1);
            compare(action.signalArguments[0][0], "hardware");
            compare(action.signalArguments[0][1], 0);
        }
        function test_controls_keyboard_and_unavailable_state() {
            waitForRendering(center);
            const dnd = findChild(center, "doNotDisturb");
            settings.notificationsInhibitedUntil = new Date(Date.now() + 3 * 3600000);
            waitForRendering(center); verify(dnd.checked); compare(settings.saves, 0);
            settings.notificationsInhibitedUntil = new Date(0);
            waitForRendering(center); verify(!dnd.checked); compare(settings.saves, 0);
            dnd.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(settings.saves, 1); verify(dnd.checked);
            keyClick(Qt.Key_Space); compare(settings.saves, 2); verify(!dnd.checked);
            const slider = findChild(center, "volumeSlider");
            verify(slider.enabled); compare(slider.value, 55);
            slider.forceActiveFocus(); keyClick(Qt.Key_Right);
            compare(action.count, 1); compare(action.signalArguments[0][0], "volume");
            compare(action.signalArguments[0][1], 56);
            const mute = findChild(center, "muteButton");
            mute.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(action.count, 2); compare(action.signalArguments[1][0], "mute");
            const lock = findChild(center, "lockButton");
            verify(lock.mapToItem(scene, 0, lock.height).y <= scene.height);
            grabImage(scene).save("artifacts/islands/center.png");
            const themes = findChild(center, "themesButton"); themes.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(action.signalArguments[2][0], "appearance");
            const preferences = findChild(center, "preferencesButton"); preferences.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(launch.signalArguments[0][0], "settings");
            scene.width = 480; waitForRendering(center);
            verify(slider.width > 120); verify(slider.mapToItem(scene, slider.width, 0).x <= scene.width);
            grabImage(scene).save("artifacts/islands/center-compact.png");
            center.systemState = {volume: null, muted: false, brightness: null, network: "Nicht verfügbar"};
            waitForRendering(center);
            verify(!slider.enabled); verify(!mute.enabled);
            verify(!findChild(center, "brightnessSlider").enabled);
        }
    }
}
