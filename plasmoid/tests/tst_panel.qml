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
    SignalSpy { id: apps; target: panel; signalName: "openApp" }
    SignalSpy { id: more; target: panel; signalName: "moreTasks" }
    SignalSpy { id: dismissed; target: panel; signalName: "dismissTask" }
    TestCase {
        name: "LumenPanel"
        when: windowShown
        function test_compact_apps_stay_above_tasks_and_launch_by_keyboard() {
            const catalog = ["lumen", "files", "search", "translate", "wissen", "inbox", "vault", "reader", "sound", "meetings", "household", "workbench", "radio"].map(id => ({id: id, title: "Lumen " + id, label: id, description: "Open " + id, icon: "lumen-" + id}));
            panel.snapshot = {apps: catalog, active: [], recent: [], error: "", busy: false, attention: false, more: true};
            for (const width of [510, 420, 340]) {
                scene.width = width; waitForRendering(panel);
                const grid = findChild(panel, "appGrid");
                compare(grid.columns, width >= 464 ? 5 : 4);
                for (const app of catalog) {
                    const tile = findChild(panel, "app-" + app.id);
                    verify(tile !== null); verify(tile.visible);
                    verify(tile.mapToItem(panel, tile.width, 0).x <= panel.width + 1);
                    verify(tile.height <= 60);
                    tile.forceActiveFocus(); keyClick(Qt.Key_Space);
                    compare(apps.signalArguments[apps.count-1][0], app.id);
                }
                grabImage(scene).save("artifacts/panel/apps-" + width + ".png");
            }
            const loadMore = findChild(panel, "moreTasksButton");
            verify(loadMore.visible); loadMore.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(more.count, 1);
            panel.loadingTasks = true; verify(!loadMore.enabled); panel.loadingTasks = false;
            scene.width = 420;
        }
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
            const cancelled = JSON.parse(JSON.stringify(panel.snapshot));
            cancelled.recent[0].status = "cancelled"; cancelled.recent[0].state = "Abgebrochen";
            panel.snapshot = cancelled; waitForRendering(panel);
            verify(close.visible); close.forceActiveFocus(); keyClick(Qt.Key_Space);
            compare(dismissed.count, 2); compare(dismissed.signalArguments[1][0], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
            const running = JSON.parse(JSON.stringify(panel.snapshot));
            running.recent[0].status = "running"; panel.snapshot = running; waitForRendering(panel);
            verify(!close.visible);
            panel.snapshot = {active: [], recent: [], busy: false, attention: false, error: "Aufträge gerade nicht lesbar."};
            waitForRendering(panel);
            compare(panel.snapshot.recent.length, 0);
        }
    }
}
