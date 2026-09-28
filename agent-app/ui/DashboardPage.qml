// Dashboard page — modern stat cards + watchdog report.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "Theme.js" as Theme
import "Paths.js" as Paths

Item {
    id: page

    property var executor
    property bool busy: false

    property string cpuUsage: "–"
    property string memUsed: "–"
    property string gpu: "–"
    property string gpuTemp: "–"
    property string disk: "–"
    property int failedCount: 0
    property string report: ""

    function refresh() {
        busy = true;
        var cmd = "echo CPU=$(top -bn1 | awk '/Cpu\\(s\\)/ {print $2}'); " +
                  "echo MEM=$(free -h | awk '/Mem:/ {print $3\" / \"$2}'); " +
                  "echo DISK=$(df -h / | awk 'NR==2 {print $5}'); " +
                  "GT=$(nvidia-smi --query-gpu=utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1); " +
                  "echo GPU=$(echo $GT | cut -d, -f1); " +
                  "echo GPUTEMP=$(echo $GT | cut -d, -f2); " +
                  "echo FAILED=$(systemctl --user --failed --no-legend 2>/dev/null | wc -l)";
        executor.run(cmd);
    }

    function loadReport() {
        executor.run("cat \"$HOME/.cache/opencode-lumen/latest-analysis.md\" 2>/dev/null || echo '(kein Report vorhanden)'");
    }

    Connections {
        target: page.executor
        function onFinished(command, code, out, err) {
            if (command.indexOf("top -bn1") !== -1) {
                out.split("\n").forEach(function (line) {
                    var i = line.indexOf("=");
                    if (i > 0) {
                        var k = line.substring(0, i).trim();
                        var v = line.substring(i + 1).trim();
                        if (k === "CPU") page.cpuUsage = v + " %";
                        else if (k === "MEM") page.memUsed = v;
                        else if (k === "DISK") page.disk = v;
                        else if (k === "GPU") page.gpu = v + " %";
                        else if (k === "GPUTEMP") page.gpuTemp = v + " °C";
                        else if (k === "FAILED") page.failedCount = parseInt(v) || 0;
                    }
                });
                page.busy = false;
            } else if (command.indexOf("latest-analysis.md") !== -1) {
                page.report = out;
            }
        }
    }

    Flickable {
        anchors.fill: parent
        contentHeight: content.implicitHeight + 36
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: content
            x: 18
            width: page.width - 36
            y: 18
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                QQC2.Label {
                    text: "Systemstatus"
                    color: Theme.text
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize + 4
                    font.bold: true
                    Layout.fillWidth: true
                }
                QQC2.Label {
                    text: page.busy ? "aktualisiere …" : "aktualisiert"
                    color: Theme.textFaint
                    font: Kirigami.Theme.smallFont
                    verticalAlignment: Text.AlignVCenter
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 14
                rowSpacing: 14

                Repeater {
                    model: [
                        { k: "CPU",     v: page.cpuUsage, i: "cpu",                 c: Theme.accent },
                        { k: "RAM",     v: page.memUsed,  i: "memory",              c: Theme.ok },
                        { k: "GPU",     v: page.gpu,      i: "video-display",       c: Theme.accent },
                        { k: "GPU-Temp",v: page.gpuTemp,  i: "temperature-normal",  c: Theme.warn },
                        { k: "Disk /",  v: page.disk,     i: "drive-harddisk",      c: Theme.accent },
                        { k: "Fehler",  v: page.failedCount, i: "dialog-warning",  c: page.failedCount > 0 ? Theme.bad : Theme.ok }
                    ]
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        radius: Theme.radius
                        color: Theme.surfaceAlt
                        border.width: 1
                        border.color: Theme.border

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 14

                            Rectangle {
                                Layout.preferredWidth: 44; Layout.preferredHeight: 44
                                radius: 12
                                color: Qt.rgba(modelData.c.r, modelData.c.g, modelData.c.b, 0.16)
                                Kirigami.Icon {
                                    anchors.centerIn: parent
                                    source: modelData.i
                                    width: 24; height: 24
                                    color: modelData.c
                                }
                            }
                            ColumnLayout {
                                spacing: 2
                                Layout.fillWidth: true
                                QQC2.Label {
                                    text: modelData.k
                                    color: Theme.textDim
                                    font: Kirigami.Theme.smallFont
                                }
                                QQC2.Label {
                                    text: String(modelData.v)
                                    color: Theme.text
                                    font.pointSize: Kirigami.Theme.defaultFont.pointSize + 3
                                    font.bold: true
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                spacing: 10
                PillButton { text: "Aktualisieren"; icon: "view-refresh"; onClicked: page.refresh() }
                PillButton {
                    text: "Wächter prüfen"; icon: "security-high"
                    onClicked: page.executor.run(Paths.binDir + "/lumen-watch; echo DONE")
                }
                PillButton { text: "Report laden"; icon: "text-x-generic"; onClicked: page.loadReport() }
                Item { Layout.fillWidth: true }
            }

            QQC2.Label {
                text: "Letzter Wächter-Report"
                color: Theme.text
                font.bold: true
                font.pointSize: Kirigami.Theme.defaultFont.pointSize + 1
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 300
                radius: Theme.radius
                color: Theme.surfaceAlt
                border.width: 1
                border.color: Theme.border

                QQC2.ScrollView {
                    anchors.fill: parent
                    anchors.margins: 6
                    QQC2.TextArea {
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.MarkdownText
                        color: Theme.text
                        text: page.report === "" ? "Noch nicht geladen." : page.report
                        background: null
                    }
                }
            }
        }
    }

    Component.onCompleted: { refresh(); loadReport(); }
}
