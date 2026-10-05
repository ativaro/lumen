import QtQuick
import QtQuick.Controls
ApplicationWindow {
    id: root
    required property var controller
    property alias page: view.page
    width: 1280; height: 900; minimumWidth: 820; minimumHeight: 620
    title: "Lumen System"; color: controller.theme.window
    System { id: view; anchors.fill: parent; controller: root.controller }
}
