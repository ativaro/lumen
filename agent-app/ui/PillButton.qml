// Small modern pill button used across the app.
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "Theme.js" as Theme

Rectangle {
    id: btn
    property string text: ""
    property string icon: ""
    property bool primary: false

    signal clicked()

    implicitWidth: row.implicitWidth + 30
    implicitHeight: 38
    radius: 19
    color: {
        if (primary) return hover.hovered ? Theme.accentDim : Theme.accent;
        return hover.hovered ? Theme.elevated : Theme.surfaceAlt;
    }
    border.width: primary ? 0 : 1
    border.color: Theme.border
    Behavior on color { ColorAnimation { duration: 120 } }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Kirigami.Icon {
            source: btn.icon
            visible: btn.icon !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: 17
            height: 17
            color: btn.primary ? "#06202e" : Theme.textDim
        }
        QQC2.Label {
            id: lbl
            anchors.verticalCenter: parent.verticalCenter
            text: btn.text
            color: btn.primary ? "#06202e" : Theme.text
            font.bold: btn.primary
            font.pointSize: Kirigami.Theme.defaultFont.pointSize
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: btn.clicked() }
}
