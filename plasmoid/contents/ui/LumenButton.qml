pragma ComponentBehavior: Bound
import QtQuick
import org.kde.kirigami as Kirigami
import QtQuick.Layouts
import org.kde.plasma.components as PC

PC.Button {
    id: button
    Kirigami.Theme.inherit: true
    property bool prominent: false
    property int symbolSize: 22
    property string hint: ""
    implicitHeight: 42
    leftPadding: 12; rightPadding: 12; topPadding: 8; bottomPadding: 8
    font.pixelSize: 15
    opacity: enabled ? 1 : 0.4
    background: Rectangle {
        radius: Math.min(height / 2, 16)
        color: button.down || button.checked ? Kirigami.Theme.alternateBackgroundColor : button.hovered ? Kirigami.Theme.alternateBackgroundColor : button.flat ? "transparent" : Kirigami.Theme.backgroundColor
        border.width: button.visualFocus ? 2 : button.flat ? 0 : 1
        border.color: button.visualFocus ? Kirigami.Theme.highlightColor : Qt.alpha(Kirigami.Theme.textColor, 0.20)
        Behavior on color { ColorAnimation { duration: 120 } }
    }
    contentItem: RowLayout {
        spacing: 10
        LumenIcon {
            visible: button.icon.name !== ""
            name: button.icon.name
            color: button.prominent ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
            Layout.preferredWidth: button.symbolSize
            Layout.preferredHeight: button.symbolSize
        }
        PC.Label {
            visible: button.text !== "" && button.display !== PC.AbstractButton.IconOnly
            text: button.text; textFormat: Text.PlainText; font: button.font
            color: Kirigami.Theme.textColor
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        PC.Label {
            visible: button.hint !== ""; text: button.hint
            font.pixelSize: 12; color: Kirigami.Theme.disabledTextColor
        }
    }
}
