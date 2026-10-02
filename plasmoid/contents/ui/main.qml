pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    property var snapshot: ({active: [], recent: [], error: "", busy: false, attention: false})
    property bool loading: false
    property string signature: ""
    property string dismissCommand: ""
    property bool discardSnapshot: false
    property string helper: "/usr/bin/lumen-panel"
    readonly property string surface: Plasmoid.configuration.surface || "tasks"
    property var systemState: ({volume: null, muted: false, brightness: null, network: "Wird geladen …"})
    property string systemError: ""
    property bool systemBusy: false
    property string systemCommand: ""
    preferredRepresentation: compactRepresentation
    toolTipMainText: surface === "search" ? "Suchen oder fragen" : surface === "control" ? "Einstellungen" : "Dein System"
    toolTipSubText: surface === "search" ? "Dateien, Apps und Gespräche in einer Suche" : surface === "control" ? "Systemregler, Einstellungen und Themes" : snapshot.error || (snapshot.attention ? "Braucht deine Rückmeldung"
        : snapshot.busy ? "Aufträge laufen" : "Aufträge, Ergebnisse und Schnellaktionen")

    function refresh() {
        if (loading || dismissCommand || surface === "search" || surface === "control") return;
        loading = true;
        runner.connectSource(helper + " --snapshot");
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
    function openTask(taskId) {
        if (!/^[0-9a-f]{32}$/.test(taskId)) return;
        runner.connectSource(helper + " --open-task " + taskId);
        expanded = false;
    }
    function dismissTask(taskId) {
        if (dismissCommand || !/^[0-9a-f]{32}$/.test(taskId)) return;
        discardSnapshot = loading;
        dismissCommand = helper + " --dismiss-task " + taskId;
        runner.connectSource(dismissCommand);
    }
    onExpandedChanged: { if (root.expanded) { refresh(); refreshSystem(); } }

    compactRepresentation: CompactBar {
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
        snapshot: root.snapshot
        dismissBusy: root.dismissCommand !== ""
        onRefresh: root.refresh()
        onLaunch: action => root.launch(action)
        onOpenTask: taskId => root.openTask(taskId)
        onDismissTask: taskId => root.dismissTask(taskId)
    } }
    Component { id: centerView; ControlCenter {
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
            if (source === root.systemCommand) {
                root.systemBusy = false;
                try {
                    if (data["exit code"] !== 0) throw new Error();
                    const response = JSON.parse(data["stdout"]);
                    root.systemError = response.error || "";
                    if (response.system) root.systemState = response.system;
                } catch (error) { root.systemError = "Systemsteuerung gerade nicht erreichbar."; }
                return;
            }
            if (source === root.dismissCommand) root.dismissCommand = "";
            else if (source === root.helper + " --snapshot") {
                root.loading = false;
                if (root.discardSnapshot) { root.discardSnapshot = false; return; }
                if (root.dismissCommand) return;
            } else return;
            try {
                if (data["exit code"] !== 0) throw new Error("Panel-Helfer nicht erreichbar.");
                const next = JSON.parse(data["stdout"]);
                if (!Array.isArray(next.active) || !Array.isArray(next.recent)) throw new Error("Ungültiger Auftragsstatus.");
                const signature = JSON.stringify(next);
                if (signature !== root.signature) {
                    root.signature = signature;
                    root.snapshot = next;
                }
            } catch (error) {
                root.signature = "";
                root.snapshot = {active: [], recent: [], busy: false, attention: false,
                    error: "Aufträge gerade nicht verfügbar. Bitte erneut aktualisieren."};
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
