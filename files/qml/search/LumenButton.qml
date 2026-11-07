pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls

Button {
    id: control
    required property var theme
    property bool primary: false
    property bool quiet: false
    property string hint: ""
    implicitHeight: theme.compact ? 34 : 40
    leftPadding: 14
    rightPadding: 14
    font.pixelSize: theme.fontSize ? theme.fontSize - 2 : 14
    font.weight: Font.Medium
    palette.buttonText: primary ? theme.onAccent : theme.text
    palette.text: primary ? theme.onAccent : theme.text
    icon.color: primary ? theme.onAccent : theme.text
    icon.width: 18
    icon.height: 18
    opacity: enabled ? 1 : 0.45
    hoverEnabled: true
    Accessible.name: text || hint
    background: Rectangle {
        radius: Math.min(control.theme.radius, 12)
        color: control.primary ? control.theme.accent : control.checked ? Qt.alpha(control.theme.accent,0.15) : control.down ? control.theme.hover : control.hovered ? Qt.alpha(control.theme.hover, 0.8) : control.quiet ? "transparent" : control.theme.button
        border.width: control.activeFocus ? 2 : control.quiet ? 0 : 1
        border.color: control.activeFocus ? control.theme.accent : Qt.alpha(control.theme.border, 0.6)
    }
    ToolTip.visible: hovered && hint.length > 0
    ToolTip.text: hint
    ToolTip.delay: 700
}
