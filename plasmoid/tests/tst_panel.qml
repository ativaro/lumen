import QtQuick
import QtTest
import org.kde.kirigami as Kirigami
import "../contents/ui" as Lumen

Rectangle {
    id: scene
    width: 420
    height: 580
    color: "#212b2f"
    Lumen.PanelView {
        id: panel
        anchors.fill: parent
        anchors.margins: 12
    }
    SignalSpy { id: dismissed; target: panel; signalName: "dismissTask" }
    TestCase {
        name: "LumenPanel"
        when: windowShown
        function test_results_keyboard_errors_and_compact_layout() {
            panel.snapshot = {active: [], recent: [
                {id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", title: "Fotos für die Familie vorbereitet",
                 state: "Erledigt", status: "completed", cursor: 3, total: 3,
                 result: "24 Bilder verkleinert. <b>Dieser Text bleibt Klartext.</b>", error: "", truncated: false}
            ], busy: false, attention: false, error: ""};
            waitForRendering(panel);
            const toggle = findChild(panel, "taskToggle-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            verify(toggle !== null);
            toggle.forceActiveFocus();
            keyClick(Qt.Key_Return);
            compare(panel.expandedTask, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            const result = findChild(panel, "taskResult-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            verify(result.visible);
            compare(result.textFormat, Text.PlainText);
            const changed = JSON.parse(JSON.stringify(panel.snapshot));
            changed.recent[0].result = "Aktualisiertes Ergebnis aus Files";
            panel.snapshot = changed;
            waitForRendering(panel);
            verify(toggle.activeFocus);
            compare(result.text, "Aktualisiertes Ergebnis aus Files");
            const close = findChild(panel, "taskClose-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            verify(close.visible); verify(close.enabled);
            panel.dismissBusy = true; verify(!close.enabled); panel.dismissBusy = false;
            close.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(dismissed.count, 1); compare(dismissed.signalArguments[0][0], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            compare(panel.expandedTask, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            scene.width = 340;
            waitForRendering(panel);
            verify(toggle.width <= panel.width);
            verify(result.width <= panel.width);
            grabImage(scene).save("artifacts/panel/menu-compact.png");
            scene.width = 420;
            waitForRendering(panel);
            grabImage(scene).save("artifacts/panel/menu.png");
            const running = JSON.parse(JSON.stringify(panel.snapshot));
            running.recent[0].status = "running"; panel.snapshot = running; waitForRendering(panel);
            verify(!close.visible);
            panel.snapshot = {active: [], recent: [], busy: false, attention: false, error: "Aufträge gerade nicht lesbar."};
            waitForRendering(panel);
            compare(panel.snapshot.recent.length, 0);
        }
    }
}
