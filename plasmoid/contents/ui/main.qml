import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id:root
    visible:false
    Plasmoid.status:PlasmaCore.Types.HiddenStatus
    Plasmoid.backgroundHints:PlasmaCore.Types.NoBackground
    property string helper:"/usr/bin/lumen-panel"
    property string uiLanguage:"de"
    property string request:Plasmoid.configuration.notificationRequest || ""
    property bool presenterEnabled:Plasmoid.configuration.presenterEnabled || false
    function updatePresenter(){host.primary=presenterEnabled}
    onPresenterEnabledChanged:Qt.callLater(updatePresenter)
    property string ping:Plasmoid.configuration.ping || ""
    function acknowledge(){Plasmoid.configuration.readyStamp=ping;Plasmoid.configuration.writeConfig()}
    onPingChanged:acknowledge()
    onRequestChanged:if(request)host.showAll()
    NotificationHost {id:host;helper:root.helper;uiLanguage:root.uiLanguage
        onUnreadChanged:{Plasmoid.configuration.unread=unread;Plasmoid.configuration.writeConfig()}
    }
    Component.onCompleted:{Qt.callLater(updatePresenter);acknowledge();language.connectSource(helper+" --language")}
    P5Support.DataSource {id:language;engine:"executable";connectedSources:[]
        onNewData:(source,data)=>{disconnectSource(source);if(data["exit code"]===0){try{const result=JSON.parse(data.stdout);if(["de","en"].includes(result.language))root.uiLanguage=result.language;}catch(error){}}}
    }
}
