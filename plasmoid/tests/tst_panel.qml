import QtQuick
import QtTest
import org.kde.kirigami as Kirigami
import "../contents/ui" as Lumen

Rectangle {
    id: scene
    width: 510
    height: panel.implicitHeight + 24
    Kirigami.Theme.inherit: false
    Kirigami.Theme.textColor: "#eff1f3"
    Kirigami.Theme.backgroundColor: "#222529"
    Kirigami.Theme.alternateBackgroundColor: "#2a2e33"
    Kirigami.Theme.disabledTextColor: "#aab1ba"
    Kirigami.Theme.highlightColor: "#d7dce2"
    color: Kirigami.Theme.backgroundColor
    Lumen.PanelView {
        id: panel
        anchors.fill: parent
        anchors.margins: 12
    }
    SignalSpy { id: apps; target: panel; signalName: "openApp" }
    SignalSpy { id: launches; target: panel; signalName: "launch" }
    TestCase {
        name: "LumenPanel"
        when: windowShown
        function test_apps_and_all_tasks_only() {
            const catalog = [
                ["lumen", "Lumen", "lumen"], ["files", "Dateien", "system-file-manager"],
                ["search", "Suche", "system-search"], ["companion", "Companion", "view-task"],
                ["translate", "Translate", "preferences-desktop-locale"], ["wissen", "Wissen", "accessories-text-editor"],
                ["inbox", "Inbox", "mail-unread"], ["notification", "Notification", "notifications"],
                ["vault", "Vault", "document-save"], ["reader", "Reader", "application-pdf"],
                ["updater", "Updater", "system-software-update"], ["system", "System", "computer"],
                ["meetings", "Meeting & Radio", "audio-input-microphone"], ["household", "Haushalt", "view-calendar"],
                ["workbench", "Projekte", "folder-development"]
            ].map(app => ({id: app[0], title: "Lumen " + app[1], label: app[1], description: "Open " + app[1], icon: app[2]}));
            panel.uiLanguage = "de";
            panel.snapshot = {apps: catalog, active: [{id: "active", title: "ACTIVE TASK"}],
                recent: [{id: "done", title: "DONE TASK"}], error: "", busy: true, attention: true, more: true};
            for (const width of [510, 420, 340]) {
                scene.width = width; waitForRendering(panel);
                const grid = findChild(panel, "appGrid");
                compare(grid.columns, width >= 464 ? 5 : 4);
                for (const app of catalog) {
                    const tile = findChild(panel, "app-" + app.id);
                    verify(tile !== null); verify(tile.visible);
                    verify(tile.mapToItem(panel, tile.width, 0).x <= panel.width + 1);
                    const icon = findChild(panel, "appIcon-" + app.id);
                    verify(icon.width >= 40); verify(icon.height >= 40);
                    tile.forceActiveFocus(); keyClick(Qt.Key_Space);
                    compare(apps.signalArguments[apps.count-1][0], app.id);
                }
                const tasks = findChild(panel, "allTasksButton");
                verify(tasks.visible); tasks.forceActiveFocus(); keyClick(Qt.Key_Space);
                compare(launches.signalArguments[launches.count-1][0], "tasks");
                verify(tasks.mapToItem(panel, 0, tasks.height).y <= panel.height + 1);
                verify(panel.height < 470);
                compare(findChild(panel, "moreTasksButton"), null);
                compare(findChild(panel, "taskToggle-active"), null);
                compare(findChild(panel, "taskToggle-done"), null);
                grabImage(scene).save("artifacts/panel/apps-" + width + ".png");
            }
            panel.snapshot = {apps: catalog, active: [], recent: [], error: "Tasks unavailable", busy: false, attention: false};
            panel.uiLanguage = "en"; waitForRendering(panel);
            const tasks = findChild(panel, "allTasksButton");
            compare(tasks.text, "All tasks");
            verify(tasks.visible); tasks.forceActiveFocus(); keyClick(Qt.Key_Return);
            compare(launches.signalArguments[launches.count-1][0], "tasks");
        }
    }
}
