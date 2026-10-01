pragma ComponentBehavior: Bound
import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC

PC.Slider {
    id: slider
    implicitHeight: 24
    opacity: enabled ? 1 : 0.4
    background: Rectangle {
        x: slider.leftPadding; y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: slider.availableWidth; height: 5; radius: 3; color: Kirigami.Theme.disabledTextColor
        Rectangle { width: slider.visualPosition * parent.width; height: parent.height; radius: 3; color: Kirigami.Theme.highlightColor }
    }
    handle: Rectangle {
        x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: 18; height: 18; radius: 9
        color: slider.pressed ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
        border.width: slider.visualFocus ? 3 : 0; border.color: Kirigami.Theme.highlightColor
    }
}
