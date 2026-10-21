import QtQuick
import QtQuick.Window

Image {
    id: halo
    objectName: "lumenThinkingMark"
    property bool active: false
    property bool reduceMotion: Application.styleHints.accessibility !== undefined && Application.styleHints.accessibility.motionPreference === Qt.ReducedMotion
    source: Qt.resolvedUrl("lumen-mark.svg")
    sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
    fillMode: Image.PreserveAspectFit
    smooth: true
    width: 24
    height: 24
    Accessible.ignored: true
    RotationAnimation on rotation {
        from: 0; to: 360; duration: 1600; loops: Animation.Infinite
        running: halo.active && halo.visible && halo.Window.window !== null && halo.Window.window.visible && !halo.reduceMotion
        onStopped: halo.rotation = 0
    }
}
