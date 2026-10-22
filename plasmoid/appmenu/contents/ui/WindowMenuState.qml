import QtQuick
import QtQml.Models
import org.kde.taskmanager as TaskManager

QtObject {
    id: state
    property rect screenGeometry
    property QtObject activeWindow: null
    property bool holdActiveWindow: false
    onHoldActiveWindowChanged: if (!holdActiveWindow) selectActiveWindow()
    function selectActiveWindow() {
        if (holdActiveWindow) return;
        for (let i = 0; i < windows.count; ++i) {
            const window = windows.objectAt(i);
            if (window && window.active) { activeWindow = window; return; }
        }
        activeWindow = null;
    }
    readonly property bool maximized: activeWindow ? activeWindow.model.IsMaximized : false
    readonly property bool fullScreen: activeWindow ? activeWindow.model.IsFullScreen : false
    readonly property bool hasMenu: activeWindow ? !!activeWindow.model.ApplicationMenuServiceName && !!activeWindow.model.ApplicationMenuObjectPath : false
    readonly property string appName: activeWindow ? activeWindow.model.AppName : ""
    property var windowModel: TaskManager.TasksModel {
        groupMode: TaskManager.TasksModel.GroupDisabled
        filterByScreen: true
        screenGeometry: state.screenGeometry
    }
    property Instantiator windows: Instantiator {
        model: state.windowModel
        delegate: QtObject {
            id: window
            required property var model
            readonly property bool active: model.IsActive
            function update() {
                if (state.holdActiveWindow) return;
                if (active) state.activeWindow = window;
                else if (state.activeWindow === window) state.selectActiveWindow();
            }
            onActiveChanged: update()
            Component.onCompleted: update()
            Component.onDestruction: if (state.activeWindow === window) state.activeWindow = null
        }
    }
}
