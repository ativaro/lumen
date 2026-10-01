import QtQuick
import QtTest
import "../contents/ui" as Lumen

Rectangle {
    id: scene
    width: 480; height: 56; radius: 28; color: "#212b2f"
    Lumen.CompactBar { id: bar; anchors.fill: parent; anchors.margins: 6 }
    SignalSpy { id: toggles; target: bar; signalName: "toggle" }
    SignalSpy { id: launches; target: bar; signalName: "launch" }
    SignalSpy { id: searches; target: bar; signalName: "search" }
    TestCase {
        name: "LumenCompactBar"; when: windowShown
        function verifyCentered(button) {
            const icon = button.contentItem.children[0];
            verify(Math.abs(icon.mapToItem(scene, 0, icon.height / 2).y - scene.height / 2) <= 0.5,
                   button.objectName + " icon must share the panel's vertical center");
        }
        function test_roles_keyboard_and_bounds() {
            scene.height = 48; scene.width = 280; bar.surface = "home"; waitForRendering(bar);
            const home = findChild(bar, "homeButton"); const files = findChild(bar, "filesButton");
            verifyCentered(home); verifyCentered(files);
            verify(home.width > 90); verify(files.mapToItem(scene, files.width, 0).x <= scene.width);
            home.forceActiveFocus(); keyClick(Qt.Key_Space); compare(toggles.count, 1);
            files.forceActiveFocus(); keyClick(Qt.Key_Space); compare(launches.signalArguments[0][0], "files");
            grabImage(scene).save("artifacts/islands/bar-home.png");
            scene.width = 480; bar.surface = "search"; waitForRendering(bar);
            const search = findChild(bar, "searchButton"); search.forceActiveFocus(); keyClick(Qt.Key_Space);
            verifyCentered(search);
            compare(searches.count, 1); verify(search.width > 440);
            compare(findChild(bar, "askButton"), null); compare(launches.count, 1);
            grabImage(scene).save("artifacts/islands/bar-search.png");
            scene.width = 74; bar.surface = "control"; waitForRendering(bar);
            const center = findChild(bar, "centerButton"); center.forceActiveFocus(); keyClick(Qt.Key_Space);
            verifyCentered(center);
            compare(toggles.count, 2); verify(center.mapToItem(scene, center.width, 0).x <= scene.width);
        }
    }
}
