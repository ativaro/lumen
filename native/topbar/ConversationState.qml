import QtQuick

QtObject {
    id: state
    required property var model
    required property var translate
    required property var colors
    readonly property var data:model.state
    readonly property var messages:data.messages||[]
    readonly property var permissions:data.permissions||[]
    readonly property var questions:data.questions||[]
    readonly property bool busy:!!data.busy
    readonly property string error:data.error||""
    readonly property string status:data.status||translate("Gespräch wird geöffnet …")
    readonly property var theme:Object.assign({fontSize:14,fontFamily:Qt.application.font.family,rowHeight:40,button:colors.window,hover:colors.base},colors,data.theme||{})
    signal answerChecksChanged()
    onDataChanged:answerChecksChanged()
    function text(value){return data.labels?.[value]||translate(value)}
    function open_link(link){model.call("open_link",[link])}
    function check_answer_item(message,key,checked){model.call("check",[message,key,checked])}
    function answer_item_checked(message,key,value){
        const row=messages.find(m=>m.key===message)
        for(const block of row?.blocks||[])for(const item of block.items||[])if(item.key===key)return item.checked
        return value
    }
    function answer_table(block,width){return block.body||""}
    function permission_reply(identity,allow){model.call("permission",[identity,allow])}
    function question_reply(identity,answers){model.call("question",[identity,answers])}
    function skip_question(identity){model.call("reject_question",[identity])}
    readonly property QtObject richView:QtObject {
        readonly property var data:state.data.rich||({})
        readonly property var blocks:data.blocks||[]
        readonly property var values:data.values||({})
        readonly property string title:data.title||""
        readonly property string submitLabel:data.submitLabel||""
        readonly property bool active:!!data.active
        readonly property bool editable:!!data.editable
        readonly property bool canSubmit:!!data.canSubmit
        readonly property int tableRevision:data.tableRevision||0
        function text(value){return state.text(value)}
        function table_rows(key,revision){return data.rows?.[key]||[]}
        function set_value(key,value){state.model.call("rich.set_value",[key,value])}
        function filter_table(key,query){state.model.call("rich.filter_table",[key,query])}
        function sort_table(key,column){state.model.call("rich.sort_table",[key,column])}
        function select_row(key,index){state.model.call("rich.select_row",[key,index])}
        function copy_table(key){state.model.call("rich.copy_table",[key])}
        function export_table(key,path){state.model.call("rich.export_table",[key,path])}
        function open_file(key,index){state.model.call("rich.open_file",[key,index])}
        function submit(){state.model.call("rich.submit")}
    }
}
