import QtQuick
import QtQml.Models
import org.kde.taskmanager as TaskManager

QtObject {
    id: state
    property rect screenGeometry
    property QtObject activeWindow: null
    property bool holdActiveWindow: false
    onHoldActiveWindowChanged: if(!holdActiveWindow) selectActive()
    function selectActive() {
        if(holdActiveWindow)return
        for(let i=0;i<windows.count;i++) {const w=windows.objectAt(i);if(w && w.active){activeWindow=w;return}}
        // A panel or popup may own focus; keep its application until another activates or the row disappears.
    }
    readonly property bool fullScreen: activeWindow ? activeWindow.model.IsFullScreen : false
    readonly property string appName: activeWindow ? activeWindow.model.AppName || "" : ""
    readonly property string title: activeWindow ? activeWindow.model.display || "" : ""
    readonly property string service: activeWindow ? activeWindow.model.ApplicationMenuServiceName || "" : ""
    readonly property string path: activeWindow ? activeWindow.model.ApplicationMenuObjectPath || "" : ""
    readonly property bool closable:activeWindow ? activeWindow.model.IsClosable : false
    readonly property bool maximizable:activeWindow ? activeWindow.model.IsMaximizable : false
    readonly property bool minimizable:activeWindow ? activeWindow.model.IsMinimizable : false
    readonly property int pid: activeWindow ? activeWindow.model.AppPid || 0 : 0
    function action(name) {
        if(!activeWindow)return
        const index=windowModel.makeModelIndex(activeWindow.index)
        if(name==="maximize")windowModel.requestToggleMaximized(index)
        else if(name==="minimize")windowModel.requestToggleMinimized(index)
        else if(name==="close")windowModel.requestClose(index)
        else if(name==="activate")windowModel.requestActivate(index)
    }
    function activate(index){if(index>=0 && index<windowModel.count)windowModel.requestActivate(windowModel.makeModelIndex(index))}
    property var windowModel: TaskManager.TasksModel {
        groupMode: TaskManager.TasksModel.GroupDisabled
        filterByScreen: true
        screenGeometry: state.screenGeometry
    }
    property Instantiator windows: Instantiator {
        model: state.windowModel
        delegate: QtObject {
            required property var model
            required property int index
            readonly property bool active: model.IsActive
            function update(){if(!state.holdActiveWindow)state.selectActive()}
            onActiveChanged:update()
            Component.onCompleted:update()
            Component.onDestruction:if(state.activeWindow===this)state.activeWindow=null
        }
        onObjectAdded:state.selectActive()
        onObjectRemoved:state.selectActive()
    }
}
