pragma ComponentBehavior: Bound
import "Translations.js" as I18n
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    property string uiLanguage: Qt.locale().name.toLowerCase().indexOf("de") === 0 ? "de" : "en"
    function tr(source, args) { return I18n.tr(source, uiLanguage, args); }
    property var snapshot: ({active: [], recent: [], error: "", busy: false, attention: false})
    property int taskLimit: 20
    property string snapshotCommand: ""
    property bool loading: false
    property string signature: ""
    property string dismissCommand: ""
    property bool discardSnapshot: false
    property string helper: "/usr/bin/lumen-panel"
    readonly property string surface: Plasmoid.configuration.surface || "tasks"
    property var systemState: ({volume: null, muted: false, brightness: null, network: root.tr("Wird geladen …")})
    property string systemError: ""
    property bool systemBusy: false
    property string systemCommand: ""
    preferredRepresentation: compactRepresentation
    // The search surface has separate pointer targets; hover popups can cover them.
    toolTipMainText: surface === "search" ? "" : surface === "control" ? root.tr("Einstellungen") : root.tr("Dein System")
    toolTipSubText: surface === "search" ? "" : surface === "control" ? root.tr("Systemregler, Einstellungen und Themes") : snapshot.error || (snapshot.attention ? root.tr("Braucht deine Rückmeldung")
        : snapshot.busy ? root.tr("Aufträge laufen") : root.tr("Aufträge, Ergebnisse und Schnellaktionen"))

    function refresh() {
        if (loading || dismissCommand || surface === "search" || surface === "control") return;
        loading = true;
        snapshotCommand = helper + " --snapshot --task-limit " + taskLimit;
        runner.connectSource(snapshotCommand);
    }
    function refreshSystem() {
        if (systemBusy || surface !== "control") return;
        systemBusy = true;
        systemCommand = helper + " --system-snapshot";
        runner.connectSource(systemCommand);
    }
    function control(action, value) {
        if (systemBusy || ["volume", "brightness", "mute", "network", "audio", "display", "appearance", "desktop-settings", "lock"].indexOf(action) < 0) return;
        let command = helper + " --control " + action;
        if (action === "volume" || action === "brightness") {
            if (!Number.isInteger(value) || value < 0 || value > 100) return;
            command += " --value " + value;
        } else if (action !== "mute") root.expanded = false;
        systemBusy = true;
        systemCommand = command;
        runner.connectSource(command);
    }
    function launch(action) {
        if (["files", "system", "tasks", "settings", "workplace"].indexOf(action) < 0) return;
        runner.connectSource(action === "settings" ? helper + " --settings" : helper + " --open-page " + action);
        expanded = false;
    }
    function openApp(appId) {
        const apps = root.snapshot.apps || [];
        if (!apps.some(app => app.id === appId) || !/^[a-z]+$/.test(appId)) return;
        runner.connectSource(helper + " --open-app " + appId);
        expanded = false;
    }
    function openTask(taskId) {
        if (!/^[0-9a-f]{32}$/.test(taskId)) return;
        runner.connectSource(helper + " --open-task " + taskId);
        expanded = false;
    }
    function dismissTask(taskId) {
        if (dismissCommand || !/^[0-9a-f]{32}$/.test(taskId)) return;
        discardSnapshot = loading;
        dismissCommand = helper + " --dismiss-task " + taskId + " --task-limit " + taskLimit;
        runner.connectSource(dismissCommand);
    }
    Component.onCompleted: runner.connectSource(helper + " --language")
    onExpandedChanged: { if (root.expanded) { refresh(); refreshSystem(); } }

    compactRepresentation: CompactBar {
        uiLanguage: root.uiLanguage
        surface: root.surface; snapshot: root.snapshot; expanded: root.expanded
        onToggle: root.expanded = !root.expanded
        onLaunch: action => root.launch(action)
        onSearch: { root.expanded = false; runner.connectSource(root.helper + " --search"); }
        onVoice: { root.expanded = false; runner.connectSource(root.helper + " --voice"); }
    }
    fullRepresentation: Loader {
        Layout.minimumWidth: Kirigami.Units.gridUnit * (root.surface === "control" ? 26 : 20)
        Layout.preferredWidth: Kirigami.Units.gridUnit * (root.surface === "control" ? 29 : 27)
        Layout.preferredHeight: Kirigami.Units.gridUnit * (root.surface === "control" ? 32 : 30)
        sourceComponent: root.surface === "control" ? centerView : taskView
    }
    Component { id: taskView; PanelView {
        uiLanguage: root.uiLanguage
        snapshot: root.snapshot
        dismissBusy: root.dismissCommand !== ""
        canLoadMore: root.taskLimit < 1000
        loadingTasks: root.loading
        onMoreTasks: { if (!root.loading) { root.taskLimit = Math.min(1000, root.taskLimit + 20); root.refresh(); } }
        onRefresh: root.refresh()
        onLaunch: action => root.launch(action)
        onOpenApp: appId => root.openApp(appId)
        onOpenTask: taskId => root.openTask(taskId)
        onDismissTask: taskId => root.dismissTask(taskId)
    } }
    Component { id: centerView; ControlCenter {
        uiLanguage: root.uiLanguage
        systemState: root.systemState; busy: root.systemBusy; error: root.systemError
        onRefresh: root.refreshSystem()
        onLaunch: action => root.launch(action)
        onControl: (action, value) => root.control(action, value)
    } }
    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            if (source === root.helper + " --language") {
                try {
                    if (data["exit code"] === 0) {
                        const response = JSON.parse(data["stdout"]);
                        if (response.language === "de" || response.language === "en") root.uiLanguage = response.language;
                    }
                } catch (error) { /* Keep the desktop locale if the helper is unavailable. */ }
                return;
            }
            if (source === root.systemCommand) {
                root.systemBusy = false;
                try {
                    if (data["exit code"] !== 0) throw new Error();
                    const response = JSON.parse(data["stdout"]);
                    root.systemError = response.error || "";
                    if (response.system) root.systemState = response.system;
                } catch (error) { root.systemError = root.tr("Systemsteuerung gerade nicht erreichbar."); }
                return;
            }
            if (source === root.dismissCommand) root.dismissCommand = "";
            else if (source === root.snapshotCommand) {
                root.loading = false;
                if (root.discardSnapshot) { root.discardSnapshot = false; return; }
                if (root.dismissCommand) return;
            } else return;
            try {
                if (data["exit code"] !== 0) throw new Error(root.tr("Panel-Helfer nicht erreichbar."));
                const next = JSON.parse(data["stdout"]);
                if (!Array.isArray(next.active) || !Array.isArray(next.recent)) throw new Error(root.tr("Ungültiger Auftragsstatus."));
                const signature = JSON.stringify(next);
                if (signature !== root.signature) {
                    root.signature = signature;
                    root.snapshot = next;
                }
            } catch (error) {
                root.signature = "";
                root.snapshot = {apps: root.snapshot.apps || [], active: [], recent: [], busy: false, attention: false,
                    error: root.tr("Aufträge gerade nicht verfügbar. Bitte erneut aktualisieren.")};
            }
        }
    }
    Timer {
        interval: root.expanded ? 2000 : 15000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }
    Timer {
        interval: 4000; running: root.expanded && root.surface === "control"; repeat: true
        onTriggered: root.refreshSystem()
    }
}
