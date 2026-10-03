pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: meter
    required property var controller
    readonly property var theme: controller.theme
    spacing: 12
    Rectangle {
        Layout.preferredWidth: 38; Layout.preferredHeight: 38
        radius: 19; color: Qt.alpha(meter.theme.accent, 0.12)
        Rectangle {
            anchors.centerIn: parent
            width: 10 + meter.controller.voiceLevel * 12; height: width; radius: width / 2
            color: meter.theme.accent
            Behavior on width { NumberAnimation { duration: 80 } }
        }
    }
    ColumnLayout {
        spacing: 4
        Row {
            Layout.preferredHeight: 22; spacing: 3
            Repeater {
                model: 22
                Rectangle {
                    required property int index
                    width: 3; radius: 1.5; anchors.verticalCenter: parent.verticalCenter
                    height: 3 + meter.controller.voiceLevel * (8 + 13 * Math.abs(Math.sin(index * 1.7)))
                    color: meter.theme.accent
                    Behavior on height { NumberAnimation { duration: 70 } }
                }
            }
        }
        Label {
            Layout.fillWidth: true
            text: meter.controller.voiceStatus
            color: meter.theme.muted; font.pixelSize: 11
            elide: Text.ElideRight
            Accessible.name: text
        }
        Layout.fillWidth: true
    }
    LumenButton {
        theme: meter.theme; quiet: true
        text: meter.controller.text("Unterbrechen")
        visible: ["thinking", "preparing", "speaking"].indexOf(meter.controller.voiceState) >= 0
        onClicked: meter.controller.interrupt_voice()
    }
}
