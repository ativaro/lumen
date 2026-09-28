// Actions page — modern quick-action cards.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "Theme.js" as Theme
import "Paths.js" as Paths

Item {
    id: page

    property var executor
    property string status: "Bereit."

    // resolved at runtime from the shell ($HOME expands inside bash -c)
    readonly property string binDir: Paths.binDir
    readonly property string workDir: "$HOME/Documents/work"
    readonly property string opencodeBin: "$HOME/.opencode/bin/opencode"

    function launch(desc, cmd) {
        status = "▶ " + desc + " gestartet";
        executor.run(cmd + " >/dev/null 2>&1 & echo started");
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

            QQC2.Label {
                text: "Schnellaktionen"
                color: Theme.text
                font.pointSize: Kirigami.Theme.defaultFont.pointSize + 4
                font.bold: true
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 14
                rowSpacing: 14

                Repeater {
                    model: [
                        { t: "opencode öffnen", d: "Interaktives Terminal im Work-Ordner", i: "utilities-terminal",
                          c: "bash -lc 'cd \"$HOME/Documents/work\" && \"$HOME/.opencode/bin/opencode\" --continue'" },
                        { t: "Frage stellen", d: "Dialog-Eingabe → opencode", i: "comment-question",
                          c: page.binDir + "/lumen-quick ask" },
                        { t: "Zwischenablage", d: "Clipboard-Inhalt an opencode", i: "edit-paste",
                          c: page.binDir + "/lumen-quick ask-sel" },
                        { t: "Systembericht", d: "Wächter prüfen + Analyse", i: "security-high",
                          c: page.binDir + "/lumen-watch" },
                        { t: "Work-Ordner", d: "Dokumente/Work öffnen", i: "folder-open",
                          c: "bash -lc 'dolphin \"$HOME/Documents/work\"'" },
                        { t: "Watchdog-Log", d: "Ergebnisse ansehen", i: "text-x-generic",
                          c: "bash -lc '\"$LUMEN_TERM\" -e less -R \"$HOME/.cache/opencode-lumen/watch-log.txt\"'" }
                    ]
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 108
                        radius: Theme.radius
                        color: hover.hovered ? Theme.elevated : Theme.surfaceAlt
                        border.width: 1
                        border.color: hover.hovered ? Theme.accent : Theme.border
                        Behavior on color { ColorAnimation { duration: 120 } }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 14

                            Rectangle {
                                Layout.preferredWidth: 48; Layout.preferredHeight: 48
                                radius: 13
                                color: Qt.rgba(0.22, 0.74, 0.97, 0.14)
                                Kirigami.Icon {
                                    anchors.centerIn: parent
                                    source: modelData.i
                                    width: 26; height: 26
                                    color: Theme.accent
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                QQC2.Label { text: modelData.t; color: Theme.text; font.bold: true; font.pointSize: Kirigami.Theme.defaultFont.pointSize + 1 }
                                QQC2.Label { text: modelData.d; color: Theme.textDim; font: Kirigami.Theme.smallFont; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }

                            PillButton {
                                text: "Start"
                                icon: "system-run"
                                primary: true
                                onClicked: page.launch(modelData.t, modelData.c)
                            }
                        }

                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                radius: Theme.radiusSm
                color: Theme.surface
                border.width: 1
                border.color: Theme.border
                QQC2.Label {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    text: page.status
                    color: Theme.textDim
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
