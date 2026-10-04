import QtQuick
import QtQuick.Controls
Button {
    id: control
    required property var theme
    property bool selected: false
    property bool primary: false
    padding: 12; leftPadding: 18; rightPadding: 18
    hoverEnabled: true
    font.family: theme.fontFamily; font.pixelSize: theme.fontSize - 2
    Accessible.name: text
    contentItem: Text {
        text: control.text; font: control.font
        color: control.primary ? theme.onAccent : control.selected ? theme.accent : theme.text
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: Math.min(12, theme.radius)
        color: control.primary ? theme.accent : control.selected || control.hovered ? theme.hover : 'transparent'
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? theme.accent : control.selected ? theme.border : Qt.alpha(theme.border, .38)
        opacity: control.enabled ? 1 : .45
    }
}
