// Modern sidebar navigation for the Lumen app.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "Theme.js" as Theme

Rectangle {
    id: sidebar

    property int currentPage: 0
    signal navigate(int page)

    color: Theme.surface

    Rectangle {   // right hairline
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: 1
        color: Theme.border
    }

    readonly property var items: [
        { t: "Chat",      icon: "comment",                 page: 0 },
        { t: "Dashboard", icon: "utilities-system-monitor", page: 1 },
        { t: "Aktionen",  icon: "system-run",              page: 2 }
    ]

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 14
        anchors.bottomMargin: 14
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        spacing: 4

        Repeater {
            model: sidebar.items
            delegate: Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 46
                radius: Theme.radiusSm
                color: {
                    if (sidebar.currentPage === modelData.page)
                        return Theme.accentSoft;
                    return hover.hovered ? Theme.surfaceAlt : "transparent";
                }
                Behavior on color { ColorAnimation { duration: 120 } }

                Rectangle {   // active accent bar
                    visible: sidebar.currentPage === modelData.page
                    anchors { left: parent.left; verticalCenter: parent.verticalCenter }
                    width: 3; height: 22; radius: 2
                    color: Theme.accent
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 12
                    spacing: 12
                    Kirigami.Icon {
                        source: modelData.icon
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 20
                        color: sidebar.currentPage === modelData.page ? Theme.accent : Theme.textDim
                    }
                    QQC2.Label {
                        text: modelData.t
                        Layout.fillWidth: true
                        color: sidebar.currentPage === modelData.page ? Theme.text : Theme.textDim
                        font.bold: sidebar.currentPage === modelData.page
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: sidebar.navigate(modelData.page) }
            }
        }

        Item { Layout.fillHeight: true }

        // footer
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: Theme.radiusSm
            color: hoverF.hovered ? Theme.surfaceAlt : "transparent"
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                spacing: 10
                Kirigami.Icon { source: "window-close"; Layout.preferredWidth: 18; Layout.preferredHeight: 18; color: Theme.textFaint }
                QQC2.Label { text: "Beenden"; color: Theme.textFaint; Layout.fillWidth: true }
            }
            HoverHandler { id: hoverF; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: Qt.quit() }
        }
    }
}
