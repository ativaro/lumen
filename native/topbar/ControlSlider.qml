import QtQuick
import QtQuick.Controls

Slider {
    id:control
    required property var controller
    required property string action
    property string topic:""
    property string target:""
    readonly property string role:topic?topic+":"+action+":"+target:action
    property var modelValue
    readonly property bool available:typeof modelValue==="number"
    property bool pending:false
    property int desired:0
    enabled:available
    from:0;to:100;stepSize:1
    Binding {target:control;property:"value";value:control.available?control.modelValue:0;when:!control.pending;restoreMode:Binding.RestoreNone}
    onMoved:{desired=Math.round(value);pending=true;commit.restart()}
    onPressedChanged:if(!pressed && pending)commit.restart()
    Timer {id:commit;interval:180
        onTriggered:{if(control.pressed || control.controller.controlBusy){restart();return;}if(control.topic)control.controller.systemAction(control.topic,control.action,control.target,control.desired);else control.controller.control(control.action,control.desired)}
    }
    Connections {target:control.controller
        function onControlFinished(role,value){if(role===control.role && value===control.desired && !control.pressed)control.pending=false}
        function onControlFailed(role){if(role===control.role){commit.stop();control.pending=false}}
    }
}
