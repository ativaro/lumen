// opencode Agent plasmoid — panel status + quick actions.
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property int failedUnits: -1
    property real cpuPercent: -1

    preferredRepresentation: compactRepresentation

    compactRepresentation: MouseArea {
        id: compact
        implicitWidth: Kirigami.Units.iconSizes.smallMedium
        implicitHeight: Kirigami.Units.iconSizes.smallMedium
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded

        Kirigami.Icon {
            id: icon
            anchors.fill: parent
            anchors.margins: 2
            source: "opencode"
        }
        Rectangle {
            visible: root.failedUnits > 0
            width: 7; height: 7; radius: 4
            color: "#e74c3c"
            anchors.right: parent.right
            anchors.top: parent.top
        }
        QQC2.ToolTip.text: "opencode Agent — " + (root.failedUnits < 0 ? "Status unbekannt"
            : (root.failedUnits > 0 ? root.failedUnits + " fehlgeschlagene Units" : "Alles in Ordnung"))
        QQC2.ToolTip.visible: containsMouse
    }

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 20
        Layout.preferredHeight: Kirigami.Units.gridUnit * 12

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Heading { text: "opencode Agent"; level: 3; Layout.fillWidth: true }

            GridLayout {
                columns: 2
                columnSpacing: Kirigami.Units.gridUnit
                rowSpacing: Kirigami.Units.smallSpacing
                Text { text: "CPU"; color: Kirigami.Theme.textColor; opacity: 0.7 }
                Text { text: root.cpuPercent >= 0 ? root.cpuPercent.toFixed(1) + " %" : "–"; color: Kirigami.Theme.textColor; font.bold: true }
                Text { text: "Fehler"; color: Kirigami.Theme.textColor; opacity: 0.7 }
                Text { text: root.failedUnits < 0 ? "–" : "" + root.failedUnits; color: Kirigami.Theme.textColor; font.bold: true }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                ActionButton { label: "App öffnen"; onActivated: root.run("opencode-agent-app") }
                ActionButton { label: "Systembericht"; onActivated: root.run("alacritty -e opencode-watch") }
                Item { Layout.fillWidth: true }
            }
        }
    }

    component ActionButton: Rectangle {
        id: btn
        property string label: ""
        signal activated()
        implicitWidth: lbl.implicitWidth + 22
        implicitHeight: 30
        radius: 6
        color: ma.hovered ? Kirigami.Theme.hoverColor : Qt.rgba(1, 1, 1, 0.08)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.18)
        Text { id: lbl; anchors.centerIn: parent; text: btn.label; color: Kirigami.Theme.textColor }
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; onClicked: btn.activated() }
    }

    function run(cmd) {
        runner.connectSource(cmd);
    }

    function refresh() {
        runner.connectSource("busctl --system call org.opencode.Agent /org/opencode/Agent org.opencode.Agent GetSummary 2>/dev/null");
    }

    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            var s = data["stdout"] || "";
            var fm = s.match(/failed_units"\s+i\s+(-?\d+)/);
            if (fm) root.failedUnits = parseInt(fm[1]);
            var cm = s.match(/cpu_percent"\s+d\s+([\d.]+)/);
            if (cm) root.cpuPercent = parseFloat(cm[1]);
        }
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }
}
