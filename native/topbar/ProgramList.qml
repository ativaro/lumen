import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.plasma.private.kicker as Kicker
import org.kde.kitemmodels as Models

ColumnLayout {
    id:programs
    required property var colors
    required property var translate
    signal launched()
    spacing:12
    Kicker.RootModel {
        id:catalogue;objectName:"programCatalogue"
        flat:true;sorted:true;showAllApps:true;showAllAppsCategorized:false
        showRecentApps:false;showRecentDocs:false;showRecentFolders:false
        showPowerSession:false;showFavoritesPlaceholder:false
    }
    Models.KSortFilterProxyModel {
        id:filtered
        sourceModel:catalogue.count?catalogue.modelForRow(0):null
        filterString:query.text.trim();filterCaseSensitivity:Qt.CaseInsensitive
    }
    function start(index){
        if(index<0 || index>=filtered.count)return
        if(filtered.sourceModel.trigger(filtered.mapToSource(filtered.index(index,0)).row,"",null))programs.launched()
        else error.text=translate("Das Programm konnte nicht gestartet werden.")
    }
    function focusSearch(){query.clear();query.forceActiveFocus()}
    TextField {
        id:query;objectName:"programSearch"
        Layout.fillWidth:true;placeholderText:translate("Programme suchen …")
        Accessible.name:placeholderText;selectByMouse:true
        palette.text:programs.colors.text;palette.placeholderText:programs.colors.muted
        background:Rectangle {color:programs.colors.base;radius:7;border.color:query.activeFocus?programs.colors.accent:programs.colors.border}
        onTextChanged:{list.currentIndex=0;error.text=""}
        onAccepted:programs.start(list.currentIndex)
        Keys.onDownPressed:{list.forceActiveFocus();list.currentIndex=Math.min(list.currentIndex+1,list.count-1)}
    }
    ListView {
        id:list;objectName:"programList"
        Layout.fillWidth:true;Layout.preferredHeight:Math.min(330,contentHeight)
        clip:true;model:filtered;currentIndex:0;keyNavigationEnabled:true;reuseItems:true
        ScrollBar.vertical:ScrollBar {}
        Keys.onReturnPressed:programs.start(currentIndex)
        delegate:BarButton {
            required property var model;required property int index
            objectName:"program_"+index;width:ListView.view.width
            colors:programs.colors;text:model.display;glyph:model.decoration
            highlighted:ListView.isCurrentItem && list.activeFocus
            onClicked:programs.start(index)
        }
    }
    Label {visible:!filtered.count;text:translate("Keine Programme gefunden.");color:programs.colors.muted;Layout.fillWidth:true}
    Label {id:error;visible:!!text;color:programs.colors.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
}
