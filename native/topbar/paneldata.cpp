// SPDX-License-Identifier: MIT
#include "paneldata.h"
#include <QSettings>
#include <QUuid>
#include <QApplication>
#include <QFont>
#include <QLabel>
#include <QStylePainter>
#include <QStyleOption>
#include <QQuickItem>
#include <QCursor>
#include <QDBusConnection>
#include <QDBusServiceWatcher>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusArgument>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPalette>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QScreen>
#include <QStandardPaths>
#include <LayerShellQt/Window>

namespace {
QVariantMap mediaMap(const QVariant &value){
    if(value.metaType()==QMetaType::fromType<QVariantMap>())return value.toMap();
    if(value.metaType()==QMetaType::fromType<QDBusArgument>() && qvariant_cast<QDBusArgument>(value).currentSignature()=="a{sv}")return qdbus_cast<QVariantMap>(value);
    return {};
}
QString mediaArtist(const QVariant &value){
    if(value.metaType()==QMetaType::fromType<QStringList>())return value.toStringList().join(", ").left(300);
    if(value.metaType()==QMetaType::fromType<QDBusArgument>() && qvariant_cast<QDBusArgument>(value).currentSignature()=="as")return qdbus_cast<QStringList>(value).join(", ").left(300);
    // Malformed third-party metadata must not reach Qt's fatal typed demarshaller.
    return {};
}
class ButtonTip:public QLabel {
public:
    ButtonTip():QLabel(nullptr,Qt::ToolTip){
        setObjectName("lumenButtonTooltip");setMargin(6);setTextFormat(Qt::PlainText);setWordWrap(true);
        setForegroundRole(QPalette::ToolTipText);setFocusPolicy(Qt::NoFocus);
        setAttribute(Qt::WA_ShowWithoutActivating);setAttribute(Qt::WA_TransparentForMouseEvents);
    }
protected:
    void paintEvent(QPaintEvent *event) override{
        QStylePainter painter(this);QStyleOption option;option.initFrom(this);
        painter.drawPrimitive(QStyle::PE_PanelTipLabel,option);painter.end();QLabel::paintEvent(event);
    }
};
QVariantMap nativePalette(){
    const auto p=QApplication::palette();
    return {{"window",p.color(QPalette::Window).name()},{"base",p.color(QPalette::Base).name()},
        {"text",p.color(QPalette::WindowText).name()},{"muted",p.color(QPalette::PlaceholderText).name()},
        {"border",p.color(QPalette::Mid).name()},{"alternate",p.color(QPalette::AlternateBase).name()},
        {"accent",p.color(QPalette::Highlight).name()},{"onAccent",p.color(QPalette::HighlightedText).name()}};
}
}

QStringList PanelData::pinnedApps() const {
    return QSettings("Lumen","Assistant").value("topbar/pinnedApps",QStringList{
        "preferred://browser","lumen-files.desktop","lumen.desktop",
        "org.kde.kate.desktop","steam.desktop","org.kde.elisa.desktop"}).toStringList();
}
void PanelData::setPinnedApps(QStringList apps) {
    for(const auto &id:apps)if(id.isEmpty() || id.size()>4096 || id.contains(QRegularExpression("[\\x00-\\x1f]")))return;
    apps.removeDuplicates();
    if(apps==pinnedApps())return;
    QSettings settings("Lumen","Assistant");settings.setValue("topbar/pinnedApps",apps);settings.sync();
    if(settings.status()!=QSettings::NoError){fail(tr("Die angehefteten Apps konnten nicht gespeichert werden."));return;}
    emit pinnedAppsChanged();
}
QString PanelData::userName() const {return qEnvironmentVariable("USER",QDir::home().dirName());}

PanelData::PanelData(QObject *parent):QObject(parent) {
    auto font=QApplication::font();font.setPixelSize(14);QApplication::setFont(font);
    connect(&m_settingsWatcher,&QFileSystemWatcher::fileChanged,this,&PanelData::readLayout);
    connect(&m_settingsWatcher,&QFileSystemWatcher::directoryChanged,this,&PanelData::readLayout);
    readLayout();
    m_taskDirectory=qEnvironmentVariable("LUMEN_DATA",QDir(qEnvironmentVariable("XDG_STATE_HOME",QDir::homePath()+"/.local/state")).filePath("lumen"));
    m_taskRefresh.setSingleShot(true);m_taskRefresh.setInterval(200);
    connect(&m_taskRefresh,&QTimer::timeout,this,&PanelData::refresh);
    const auto taskChanged=[this]{watchTasks();m_taskRefresh.start();};
    connect(&m_taskWatcher,&QFileSystemWatcher::directoryChanged,this,taskChanged);
    connect(&m_taskWatcher,&QFileSystemWatcher::fileChanged,this,taskChanged);
    watchTasks();
    auto bus=QDBusConnection::sessionBus();
    bus.registerService("org.kde.kappmenuview");
    auto viewWatcher=new QDBusServiceWatcher("org.kde.kappmenuview",bus,QDBusServiceWatcher::WatchForUnregistration,this);
    connect(viewWatcher,&QDBusServiceWatcher::serviceUnregistered,this,[]{QDBusConnection::sessionBus().registerService("org.kde.kappmenuview");});
    bus.connect("org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","NameOwnerChanged",this,SLOT(mediaOwnerChanged(QString,QString,QString)));
    bus.connect({},"/org/mpris/MediaPlayer2","org.freedesktop.DBus.Properties","PropertiesChanged","sa{sv}as",this,SLOT(mediaPropertiesChanged(QString,QVariantMap,QStringList)));
    QTimer::singleShot(0,this,&PanelData::refreshMedia);
    const QString directory=qEnvironmentVariable("LUMEN_BIN_DIR",QCoreApplication::applicationDirPath());
    const QString local=QDir(directory).filePath("lumen-panel");
    m_helper=QFileInfo(local).isExecutable()?local:QStandardPaths::findExecutable("lumen-panel");
    m_snapshot={{"apps",QVariantList{}},{"system",QVariantMap{}},{"operations",QVariantMap{}},{"palette",nativePalette()}};
    m_read.setProcessChannelMode(QProcess::SeparateChannels);m_timeout.setSingleShot(true);m_timeout.setInterval(15000);
    connect(&m_timeout,&QTimer::timeout,this,[this]{m_read.kill();fail(tr("Die Systemdaten antworten gerade nicht."));});
    connect(&m_read,&QProcess::readyReadStandardError,this,[this]{m_read.readAllStandardError();});
    connect(&m_read,&QProcess::readyReadStandardOutput,this,[this]{if(m_read.bytesAvailable()>1024*1024){m_read.kill();fail(tr("Ungültige Systemdaten."));}});
    connect(&m_read,&QProcess::errorOccurred,this,[this](QProcess::ProcessError e){if(e==QProcess::FailedToStart){m_timeout.stop();fail(tr("Der Lumen-Leistenhelfer konnte nicht gestartet werden."));}});
    connect(&m_read,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus status){
        m_timeout.stop();if(m_ignoreRead){m_ignoreRead=false;QTimer::singleShot(0,this,&PanelData::refresh);return;}const auto bytes=m_read.readAllStandardOutput();
        if(code || status!=QProcess::NormalExit || bytes.size()>1024*1024){fail(tr("Die Systemdaten konnten nicht geladen werden."));return;}
        QJsonParseError error;const auto document=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !document.isObject() || document["version"].toInt()!=1 || !document["apps"].isArray()){
            fail(tr("Ungültige Systemdaten."));return;
        }
        m_snapshot=document.object().toVariantMap();
        if(document["palette"].isNull()){QPalette system;system.setResolveMask(0);QApplication::setPalette(system);m_snapshot["palette"]=nativePalette();}
        else applyPalette(m_snapshot["palette"].toMap());
        if(!m_error.isEmpty()){m_error.clear();emit errorChanged();}emit changed();
    });
    m_poll.setInterval(10000);connect(&m_poll,&QTimer::timeout,this,&PanelData::refresh);m_poll.start();
    QTimer::singleShot(0,this,&PanelData::refresh);
}
PanelData::~PanelData(){
    m_poll.stop();m_timeout.stop();m_read.disconnect(this);
    // QProcess may emit finished while its destructor waits; our other members must still exist.
    if(m_read.state()!=QProcess::NotRunning){m_read.kill();m_read.waitForFinished(1000);}
    for(auto command:findChildren<QProcess*>(QString(),Qt::FindDirectChildrenOnly)){
        command->disconnect(this);
        if(command->state()!=QProcess::NotRunning){command->kill();command->waitForFinished(1000);}
    }
}
void PanelData::fail(const QString &message){if(message!=m_error){m_error=message;emit errorChanged();}}
void PanelData::refresh(){if(m_read.state()!=QProcess::NotRunning || controlBusy())return;if(m_helper.isEmpty()){fail(tr("Lumen ist nicht vollständig installiert."));return;}m_read.start(m_helper,{"--bar-snapshot"});m_timeout.start();}
void PanelData::watchTasks(){
    for(const auto &path:{m_taskDirectory,QFileInfo(m_taskDirectory).absolutePath(),QDir(m_taskDirectory).filePath("lumen.sqlite3"),QDir(m_taskDirectory).filePath("lumen.sqlite3-wal")})
        if(QFileInfo::exists(path) && !m_taskWatcher.files().contains(path) && !m_taskWatcher.directories().contains(path))m_taskWatcher.addPath(path);
}
void PanelData::applyPalette(const QVariantMap &colors){
    const QList<QPair<QPalette::ColorRole,QString>> roles={{QPalette::Window,"window"},{QPalette::Base,"base"},
        {QPalette::WindowText,"text"},{QPalette::Text,"text"},{QPalette::ButtonText,"text"},{QPalette::Button,"window"},
        {QPalette::Mid,"border"},{QPalette::Midlight,"alternate"},{QPalette::Highlight,"accent"},
        {QPalette::HighlightedText,"onAccent"},{QPalette::PlaceholderText,"muted"},{QPalette::AlternateBase,"alternate"}};
    auto p=QApplication::palette();for(const auto &[role,key]:roles){const QColor color(colors[key].toString());if(color.isValid())p.setColor(role,color);}for(auto role:{QPalette::WindowText,QPalette::Text,QPalette::ButtonText})p.setColor(QPalette::Disabled,role,QColor(colors["muted"].toString()));
    p.setColor(QPalette::ToolTipBase,QColor(colors["window"].toString()));p.setColor(QPalette::ToolTipText,QColor(colors["text"].toString()));QApplication::setPalette(p);
}
void PanelData::tooltip(QQuickItem *anchor,const QString &text){
    if(text.isEmpty()){
        if(m_tooltipOwner==anchor){if(m_tooltip)m_tooltip->hide();disconnect(m_tooltipDestroyed);m_tooltipOwner.clear();}
        return;
    }
    if(!anchor || !anchor->window() || !anchor->window()->isVisible() || !anchor->isVisible() || !anchor->isEnabled())return;
    if(m_tooltipOwner!=anchor){
        disconnect(m_tooltipDestroyed);m_tooltipOwner=anchor;
        m_tooltipDestroyed=connect(anchor,&QObject::destroyed,this,[this]{if(m_tooltip)m_tooltip->hide();m_tooltipOwner.clear();});
    }
    auto position=anchor->mapToGlobal(QPointF(0,anchor->height()+6)).toPoint();
    const auto bounds=anchor->window()->screen()->availableGeometry().adjusted(4,4,-4,-4);
    if(!m_tooltip)m_tooltip=std::make_unique<ButtonTip>();
    m_tooltip->setScreen(anchor->window()->screen());m_tooltip->setMaximumSize(qMin(360,bounds.width()),bounds.height());
    m_tooltip->setText(text.left(4096));m_tooltip->setWordWrap(m_tooltip->fontMetrics().horizontalAdvance(m_tooltip->text())>m_tooltip->maximumWidth()-12);
    m_tooltip->adjustSize();m_tooltip->winId();
    position.setX(qBound(bounds.left(),position.x(),bounds.right()-m_tooltip->width()+1));
    position.setY(qBound(bounds.top(),position.y(),bounds.bottom()-m_tooltip->height()+1));
    // Wayland popups need the layer window as transient parent before they are shown.
    m_tooltip->windowHandle()->setTransientParent(anchor->window());m_tooltip->move(position);m_tooltip->show();
}
void PanelData::start(const QStringList &arguments){
    if(m_helper.isEmpty() || !QProcess::startDetached(m_helper,arguments))fail(tr("Die Aktion konnte nicht gestartet werden."));
}
void PanelData::launch(const QString &action,const QString &value){
    if(action=="search")start({"--search"});
    else if(action=="voice")start({"--voice"});
    else if(action=="files")start({"--open-app","files"});
    else if(action=="tasks")start({"--open-page","tasks"});
    else if(action=="notifications")start({"--open-app","notification"});
    else if(action=="settings")start({"--settings"});
    else if(action=="transfer"){
        static const QRegularExpression id(QStringLiteral("^[a-f0-9]{32}$"));
        if(id.match(value).hasMatch())start({"--topbar-transfer",value});
    }else if(action=="app"){
        for(const auto &entry:m_snapshot["apps"].toList())if(entry.toMap()["id"].toString()==value){start({"--open-app",value});return;}
    }
}
void PanelData::actionError(const QString &action,const QString &message){
    m_actionError=message;emit errorChanged();emit controlFailed(action);
}
void PanelData::control(const QString &action,int value){
    static const QStringList actions={"volume","brightness","mute","network","proxy","audio","bluetooth","firewall","display","appearance","hardware","desktop-settings","lock","search"};
    if(!actions.contains(action))return;
    const bool numeric=action=="volume" || action=="brightness";
    if(numeric && (value<0 || value>100))return;
    QStringList arguments={"--control",action};if(numeric)arguments.append({"--value",QString::number(value)});
    runHelper(arguments,action,value);
}
void PanelData::inspect(const QString &topic){
    if(!QStringList{"network","audio","activity","recent"}.contains(topic) || controlBusy())return;
    runHelper({"--system-topic",topic},topic+":inspect");
}
void PanelData::systemAction(const QString &topic,const QString &action,const QString &target,int value){
    if(!QStringList{"network","audio","activity","recent"}.contains(topic) || action.size()>64 || target.size()>4096 || target.contains(QChar::Null) || controlBusy())return;
    const auto payload=QJsonDocument(QJsonObject{{"action",action},{"target",target},{"value",value}}).toJson(QJsonDocument::Compact);
    runHelper({"--system-topic",topic,"--system-action"},topic+":"+action+":"+target,value,payload);
}
QString PanelData::attachNote(int pid){
    const QString action="note:"+QUuid::createUuid().toString(QUuid::WithoutBraces);
    QTimer::singleShot(0,this,[this,pid,action]{
        if(pid<2){actionError(action,tr("Ungültiges Notes-Fenster."));return;}
        runHelper({"--topbar-note",QString::number(pid)},action);
    });
    return action;
}
QString PanelData::ask(const QString &prompt,const QVariantMap &note){
    const QString action="ask:"+QUuid::createUuid().toString(QUuid::WithoutBraces);
    const auto reject=[&](const QString &message){QTimer::singleShot(0,this,[this,action,message]{actionError(action,message);});return action;};
    if(prompt.trimmed().isEmpty() || prompt.size()>4000 || prompt.contains(QChar::Null))return reject(tr("Bitte eine Frage mit höchstens 4000 Zeichen eingeben."));
    if(m_helper.isEmpty())return reject(tr("Lumen ist nicht vollständig installiert."));
    QJsonObject request{{"prompt",prompt}};
    if(!note.isEmpty()){
        const auto object=QJsonObject::fromVariantMap(note);
        if(QJsonDocument(object).toJson(QJsonDocument::Compact).size()>16000)return reject(tr("Ungültige Notes-Auswahl."));
        request["note"]=object;
    }
    const auto payload=QJsonDocument(request).toJson(QJsonDocument::Compact);
    QTimer::singleShot(0,this,[this,action,payload]{runHelper({"--ask"},action,0,payload);});
    return action;
}
void PanelData::runHelper(const QStringList &arguments,const QString &action,int value,const QByteArray &input){
    const bool topicAction=action.startsWith("network:") || action.startsWith("audio:") || action.startsWith("activity:") || action.startsWith("recent:");
    const bool mutating=action=="volume" || action=="brightness" || action=="mute" || topicAction;
    if(mutating && controlBusy())return;
    if(m_helper.isEmpty()){actionError(action,tr("Lumen ist nicht vollständig installiert."));return;}
    m_actionError.clear();emit errorChanged();
    if(mutating && m_read.state()!=QProcess::NotRunning){m_ignoreRead=true;m_timeout.stop();m_read.kill();}
    auto command=new QProcess(this);auto timeout=new QTimer(command);timeout->setSingleShot(true);timeout->setInterval(topicAction?60000:action.startsWith("note:")?45000:15000);
    if(mutating){m_control=command;connect(command,&QProcess::stateChanged,this,[this]{emit controlBusyChanged();});}
    connect(timeout,&QTimer::timeout,command,[command]{command->setProperty("timedOut",true);command->kill();});
    connect(command,&QProcess::readyReadStandardError,command,[command]{command->readAllStandardError();});
    connect(command,&QProcess::readyReadStandardOutput,command,[command]{if(command->bytesAvailable()>1024*1024)command->kill();});
    connect(command,&QProcess::errorOccurred,this,[this,command,timeout,action](QProcess::ProcessError error){
        if(error==QProcess::FailedToStart){timeout->stop();actionError(action,tr("Die Aktion konnte nicht gestartet werden."));command->deleteLater();}
    });
    connect(command,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this,command,timeout,action,value,mutating](int code,QProcess::ExitStatus status){
        timeout->stop();if(m_control==command)m_control.clear();
        const auto bytes=command->readAllStandardOutput();QJsonParseError error;
        const auto result=QJsonDocument::fromJson(bytes,&error);QString failure;
        if(command->property("timedOut").toBool())failure=tr("Die Systemaktion wurde nicht bestätigt. Bitte den Status prüfen.");
        else if(code || status!=QProcess::NormalExit || bytes.size()>1024*1024 || error.error!=QJsonParseError::NoError || !result.isObject() || !result["error"].isString())failure=tr("Ungültige Systemdaten.");
        else failure=result["error"].toString().left(200);
        const bool topicAction=action.startsWith("network:") || action.startsWith("audio:") || action.startsWith("activity:") || action.startsWith("recent:");
        if(failure.isEmpty() && mutating && !topicAction && !result["system"].isObject())failure=tr("Ungültige Systemdaten.");
        if(failure.isEmpty() && topicAction && (!result["details"].isObject() || result["topic"].toString()!=action.section(':',0,0)))failure=tr("Ungültige Systemdaten.");
        if(failure.isEmpty() && action.startsWith("note:") && !result["note"].isObject())failure=tr("Ungültige Notes-Auswahl.");
        if(!failure.isEmpty())actionError(action,failure);
        else{
            if(action.startsWith("note:"))emit noteAttached(action,result["note"].toObject().toVariantMap());
            if(topicAction){m_details[action.section(':',0,0)]=result["details"].toObject().toVariantMap();emit detailsChanged();
                if(action.startsWith("activity:")){m_snapshot["activity"]=result["details"].toObject().toVariantMap();emit changed();}}
            else if(mutating){m_snapshot["system"]=result["system"].toObject().toVariantMap();emit changed();}
            emit controlFinished(action,value);
        }
        command->deleteLater();if(mutating)refresh();
    });
    command->start(m_helper,arguments);timeout->start();
    if(!input.isEmpty()){command->write(input);command->closeWriteChannel();}
}

void PanelData::context(const QString &app,const QString &title,int pid){
    if((app=="Lumen Reader" || app=="Reader") && pid>1){start({"--topbar-reader",QString::number(pid)});return;}
    static const QStringList browsers={"Chromium","Google Chrome","Brave","Mozilla Firefox","Microsoft Edge","Vivaldi"};
    if(browsers.contains(app) && title.size()<=4000){const auto data=QJsonDocument(QJsonObject{{"title",title},{"app",app}}).toJson(QJsonDocument::Compact).toBase64();start({"--topbar-page",QString::fromLatin1(data)});}
}
void PanelData::readLayout(){
    QSettings settings("Lumen","Assistant");settings.sync();
    auto value=settings.value("topbar/layout","classic").toString();
    if(!QStringList{"classic","band","deck","context"}.contains(value))value="classic";
    if(value!=m_layout){m_layout=value;emit layoutChanged();}
    const QFileInfo file(settings.fileName());
    // QSettings replaces files atomically; watch the directory and re-arm the file watch.
    for(const auto &path:{file.absoluteFilePath(),file.absolutePath(),QFileInfo(file.absolutePath()).absolutePath()})
        if(QFileInfo::exists(path) && !m_settingsWatcher.files().contains(path) && !m_settingsWatcher.directories().contains(path))m_settingsWatcher.addPath(path);
}
void PanelData::inputMask(QQuickWindow *window,const QVariantList &rectangles,bool popupOpen){
    if(!window)return;
    QRegion mask;
    for(const auto &value:rectangles){const auto r=value.toRect();if(r.isValid())mask+=r;}
    window->setMask(mask);
    LayerShellQt::Window::get(window)->setExclusiveZone(window->property("barSize").toInt());
    // Popups opened with Meta need keyboard focus without a preceding pointer event.
    LayerShellQt::Window::get(window)->setKeyboardInteractivity(popupOpen
        ?LayerShellQt::Window::KeyboardInteractivityExclusive:LayerShellQt::Window::KeyboardInteractivityOnDemand);
    // Wayland applies input regions on the next surface commit, even if no pixels changed.
    window->update();
}
void PanelData::ShowApps(){auto screen=QGuiApplication::screenAt(QCursor::pos());if(!screen)screen=QGuiApplication::primaryScreen();if(screen)emit showAppsRequested(screen->name());}

QVariantList PanelData::players() const{
    QVariantList result;
    for(const auto &player:m_players)if(player["playing"].toBool())result.append(player);
    for(const auto &player:m_players)if(!player["playing"].toBool())result.append(player);
    return result;
}
void PanelData::mediaPropertiesChanged(const QString &interface,const QVariantMap &,const QStringList &){
    if(interface=="org.mpris.MediaPlayer2.Player")QTimer::singleShot(0,this,&PanelData::refreshMedia);
}
void PanelData::mediaOwnerChanged(const QString &name,const QString &,const QString &newOwner){
    if(!name.startsWith("org.mpris.MediaPlayer2."))return;
    Q_UNUSED(newOwner)
    ++m_playerEpochs[name];
    if(m_players.remove(name))emit playersChanged();
    QTimer::singleShot(0,this,&PanelData::refreshMedia);
}
void PanelData::refreshMedia(){
    if(m_mediaScanning){m_mediaAgain=true;return;}
    m_mediaScanning=true;
    const auto bus=QDBusConnection::sessionBus();
    const auto message=QDBusMessage::createMethodCall("org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","ListNames");
    auto list=new QDBusPendingCallWatcher(bus.asyncCall(message,1000),this);
    connect(list,&QDBusPendingCallWatcher::finished,this,[this,list,bus]{
    m_mediaScanning=false;const QDBusPendingReply<QStringList> names=*list;list->deleteLater();
    if(!names.isValid())return;
    QSet<QString> live;
    for(const auto &name:names.value())if(name.startsWith("org.mpris.MediaPlayer2."))live.insert(name);
    bool removed=false;
    for(const auto &name:m_players.keys())if(!live.contains(name)){m_players.remove(name);removed=true;}
    if(removed)emit playersChanged();
    for(const auto &name:live){
        if(m_pendingPlayers.contains(name)){m_mediaAgain=true;continue;}
        m_pendingPlayers.insert(name);
        const auto epoch=m_playerEpochs.value(name);
        auto message=QDBusMessage::createMethodCall(name,"/org/mpris/MediaPlayer2","org.freedesktop.DBus.Properties","GetAll");
        message.setAutoStartService(false);
        message.setArguments({"org.mpris.MediaPlayer2.Player"});
        auto watcher=new QDBusPendingCallWatcher(bus.asyncCall(message,1000),this);
        connect(watcher,&QDBusPendingCallWatcher::finished,this,[this,watcher,name,epoch]{
            const QDBusPendingReply<QVariantMap> reply=*watcher;m_pendingPlayers.remove(name);
            // A reply from the old owner must never resurrect a closed/replaced player.
            if(epoch!=m_playerEpochs.value(name)){watcher->deleteLater();QTimer::singleShot(0,this,&PanelData::refreshMedia);return;}
            if(reply.isValid()){
                const auto props=reply.value();const auto metadata=mediaMap(props.value("Metadata"));
                const auto artist=mediaArtist(metadata.value("xesam:artist"));
                const QVariantMap player={{"id",name},{"app",name.mid(23).section('.',0,0)},
                    {"title",metadata.value("xesam:title").toString().left(300)},{"artist",artist.left(300)},
                    {"playing",props.value("PlaybackStatus")=="Playing"},{"control",props.value("CanControl").toBool()},
                    {"next",props.value("CanGoNext").toBool()},{"previous",props.value("CanGoPrevious").toBool()},
                    {"play",props.value("CanPlay").toBool()},{"pause",props.value("CanPause").toBool()}};
                if(m_players.value(name)!=player){m_players[name]=player;emit playersChanged();}
            }else if(m_players.remove(name))emit playersChanged();
            watcher->deleteLater();
            if(m_mediaAgain){m_mediaAgain=false;QTimer::singleShot(0,this,&PanelData::refreshMedia);}
        });
    }
    if(m_mediaAgain && m_pendingPlayers.isEmpty()){m_mediaAgain=false;QTimer::singleShot(0,this,&PanelData::refreshMedia);}
    });
}
void PanelData::mediaAction(const QString &service,const QString &action){
    const auto player=m_players.value(service);
    if(!player.value("control").toBool())return;
    if(action=="Next" && !player.value("next").toBool())return;
    if(action=="Previous" && !player.value("previous").toBool())return;
    if(action=="PlayPause" && !player.value(player.value("playing").toBool()?"pause":"play").toBool())return;
    if(!QStringList{"Next","Previous","PlayPause"}.contains(action))return;
    auto message=QDBusMessage::createMethodCall(service,"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player",action);
    message.setAutoStartService(false);
    auto watcher=new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message,2000),this);
    connect(watcher,&QDBusPendingCallWatcher::finished,this,[this,watcher]{
        const QDBusPendingReply<> reply=*watcher;
        if(reply.isError())fail(tr("Der Medienplayer hat die Aktion nicht bestätigt."));
        watcher->deleteLater();refreshMedia();
    });
}
