// Context occupies the free topbar space, outside the app-menu island.
pragma ComponentBehavior: Bound
import QtQuick
import "../../../org.lumen.appmenu/contents/ui" as Shared
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC
import "../../../org.lumen.system/contents/ui" as Lumen
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id: root
    objectName: "lumenTopbarContext"
    readonly property int widthBudget: Math.max(0, Plasmoid.configuration.widthBudget)
    readonly property string appName: windowState.appName
    readonly property bool available: windowState.activeWindow !== null && windowState.maximized && !windowState.fullScreen && widthBudget >= 80
    readonly property bool browser: /chrom|brave|firefox|edge|vivaldi/i.test(appName)
    readonly property bool reader: /Lumen Reader/i.test(appName)
    property var activity: ({})
    readonly property string activityCommand: "/usr/bin/lumen-panel --topbar-snapshot"
    Plasmoid.status: available ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.HiddenStatus
    preferredRepresentation: fullRepresentation
    Binding {
        target: Plasmoid.containment
        property: "backgroundHints"
        value: PlasmaCore.Types.NoBackground
    }
    Shared.WindowMenuState { id: windowState; screenGeometry: root.screenGeometry; holdActiveWindow: Plasmoid.containment.status === PlasmaCore.Types.AcceptingInputStatus }
    function runContext(action) {
        if (action === "page") {
            const value = Qt.btoa(JSON.stringify({title:windowState.title, app:root.appName}));
            runner.connectSource("/usr/bin/lumen-panel --topbar-page " + value);
        } else if (action === "reader" && windowState.pid > 0) runner.connectSource("/usr/bin/lumen-panel --topbar-reader " + windowState.pid);
        else if (action === "transfer" && /^[a-f0-9]{32}$/.test(activity.transfer?.id || "")) runner.connectSource("/usr/bin/lumen-panel --topbar-transfer " + activity.transfer.id);
        else if (action === "audio") runner.connectSource("/usr/bin/lumen-panel --open-app meetings");
    }
    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            if (source !== root.activityCommand) return;
            try { root.activity = data["exit code"] === 0 ? JSON.parse(data.stdout) : {}; }
            catch (error) { root.activity = {}; }
        }
    }
    Timer { interval: 3000; running: root.available; repeat: true; triggeredOnStart: true; onTriggered: runner.connectSource(root.activityCommand) }

    fullRepresentation: RowLayout {
        id: row
        readonly property bool actionVisible: root.widthBudget >= 150 && (root.browser || root.reader)
        readonly property bool operationVisible: !!(root.activity.transfer || root.activity.audio) && root.widthBudget >= (actionVisible ? 238 : 80)
        readonly property int titleWidth: Math.min(220, Math.max(0, root.widthBudget - (actionVisible ? 158 : 0) - (operationVisible ? 88 : 0)))
        spacing: 8
        Layout.minimumWidth: root.available ? implicitWidth : 0
        Layout.maximumWidth: Layout.minimumWidth
        PC.Label {
            objectName: "activeWindowContext"
            visible: row.titleWidth >= 80 && windowState.title !== ""
            text: windowState.title
            opacity: 0.75
            elide: Text.ElideRight
            Layout.minimumWidth: row.titleWidth
            Layout.maximumWidth: row.titleWidth
        }
        Lumen.LumenButton {
            flat: true; symbolSize: 18; font.pixelSize: 12
            leftPadding: 8; rightPadding: 8; topPadding: 0; bottomPadding: 0
            objectName: "activeContentAction"
            visible: row.actionVisible
            Layout.minimumWidth: 150; Layout.maximumWidth: 150
            text: root.reader ? i18n("In Lumen besprechen") : i18n("Seite merken …")
            icon.name: root.reader ? "lumen" : "bookmark-new"
            onClicked: root.runContext(root.reader ? "reader" : "page")
        }
        Lumen.LumenButton {
            flat: true; symbolSize: 18; font.pixelSize: 12
            leftPadding: 8; rightPadding: 8; topPadding: 0; bottomPadding: 0
            objectName: "activeOperation"
            visible: row.operationVisible
            Layout.minimumWidth: 80; Layout.maximumWidth: 80
            text: root.activity.audio ? i18n("Aufnahme") : root.activity.transfer ? (root.activity.transfer.percent === null ? i18n("Überträgt") : root.activity.transfer.percent + " %") : ""
            icon.name: root.activity.audio ? "audio-input-microphone" : "view-refresh"
            onClicked: root.runContext(root.activity.audio ? "audio" : "transfer")
        }
    }
}
