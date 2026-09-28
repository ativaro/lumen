// opencode Agent — main window. Lumen-styled, modern.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Effects
import org.kde.kirigami as Kirigami
import "Theme.js" as Theme

Kirigami.ApplicationWindow {
    id: root
    title: "opencode Agent"
    width: 1080
    height: 760
    minimumWidth: 720
    minimumHeight: 520
    color: Theme.bg

    Executor { id: executor }

    property int currentPage: 0
    readonly property var pageMeta: [
        { t: "Chat",      sub: "Frag opencode",        icon: "comment" },
        { t: "Dashboard", sub: "Systemstatus",          icon: "utilities-system-monitor" },
        { t: "Aktionen",  sub: "Schnellzugriff",        icon: "system-run" }
    ]

    pageStack.initialPage: Kirigami.Page {
        padding: 0
        background: Rectangle { color: Theme.bg }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // ---- Top bar ------------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: Theme.surface

                Rectangle {   // bottom hairline
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: 1
                    color: Theme.border
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 12

                    Kirigami.Icon {
                        source: "opencode"
                        Layout.preferredWidth: 26
                        Layout.preferredHeight: 26
                    }
                    QQC2.Label {
                        text: "opencode"
                        color: Theme.text
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2
                        font.bold: true
                    }
                    QQC2.Label {
                        text: "/ " + root.pageMeta[root.currentPage].t
                        color: Theme.textFaint
                        Layout.fillWidth: true
                        verticalAlignment: Text.AlignVCenter
                    }
                    QQC2.Label {
                        text: executor.busyTag !== "" ? "● arbeitet" : "● bereit"
                        color: executor.busyTag !== "" ? Theme.warn : Theme.ok
                        font: Kirigami.Theme.smallFont
                    }
                }
            }

            // ---- Body: sidebar + content --------------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Sidebar {
                    Layout.preferredWidth: 216
                    Layout.fillHeight: true
                    currentPage: root.currentPage
                    onNavigate: root.currentPage = page
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.currentPage

                    ChatPage { executor: executor }
                    DashboardPage { executor: executor }
                    ActionsPage { executor: executor }
                }
            }
        }
    }
}
