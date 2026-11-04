// SPDX-License-Identifier: MIT
#include "paneldata.h"
#include <QSettings>
#include <QFileDialog>
#include <QUuid>
#include <QApplication>
#include <QFont>
#include <QCursor>
#include <QDBusConnection>
#include <QDBusServiceWatcher>
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
QVariantMap nativePalette(){
    const auto p=QApplication::palette();
    return {{"window",p.color(QPalette::Window).name()},{"base",p.color(QPalette::Base).name()},
        {"text",p.color(QPalette::WindowText).name()},{"muted",p.color(QPalette::PlaceholderText).name()},
        {"border",p.color(QPalette::Mid).name()},{"alternate",p.color(QPalette::AlternateBase).name()},
        {"accent",p.color(QPalette::Highlight).name()},{"onAccent",p.color(QPalette::HighlightedText).name()}};
}
}

PanelData::PanelData(QObject *parent):QObject(parent) {
    auto font=QApplication::font();font.setPixelSize(14);QApplication::setFont(font);
    connect(&m_settingsWatcher,&QFileSystemWatcher::fileChanged,this,&PanelData::readLayout);
    connect(&m_settingsWatcher,&QFileSystemWatcher::directoryChanged,this,&PanelData::readLayout);
    readLayout();
    auto bus=QDBusConnection::sessionBus();
    bus.registerService("org.kde.kappmenuview");
    auto viewWatcher=new QDBusServiceWatcher("org.kde.kappmenuview",bus,QDBusServiceWatcher::WatchForUnregistration,this);
    connect(viewWatcher,&QDBusServiceWatcher::serviceUnregistered,this,[]{QDBusConnection::sessionBus().registerService("org.kde.kappmenuview");});
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
void PanelData::applyPalette(const QVariantMap &colors){
    const QList<QPair<QPalette::ColorRole,QString>> roles={{QPalette::Window,"window"},{QPalette::Base,"base"},
        {QPalette::WindowText,"text"},{QPalette::Text,"text"},{QPalette::ButtonText,"text"},{QPalette::Button,"window"},
        {QPalette::Mid,"border"},{QPalette::Midlight,"alternate"},{QPalette::Highlight,"accent"},
        {QPalette::HighlightedText,"onAccent"},{QPalette::PlaceholderText,"muted"},{QPalette::AlternateBase,"alternate"}};
    auto p=QApplication::palette();for(const auto &[role,key]:roles){const QColor color(colors[key].toString());if(color.isValid())p.setColor(role,color);}for(auto role:{QPalette::WindowText,QPalette::Text,QPalette::ButtonText})p.setColor(QPalette::Disabled,role,QColor(colors["muted"].toString()));QApplication::setPalette(p);
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
    static const QStringList actions={"volume","brightness","mute","network","audio","display","appearance","hardware","desktop-settings","lock","search"};
    if(!actions.contains(action))return;
    const bool numeric=action=="volume" || action=="brightness";
    if(numeric && (value<0 || value>100))return;
    QStringList arguments={"--control",action};if(numeric)arguments.append({"--value",QString::number(value)});
    runHelper(arguments,action,value);
}
QString PanelData::chooseAttachment(QQuickWindow *window){
    if(window)LayerShellQt::Window::get(window)->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
    const auto title=m_snapshot["labels"].toMap().value("Datei an Lumen anhängen",tr("Datei an Lumen anhängen")).toString();
    return QFileDialog::getOpenFileName(nullptr,title);
}
QString PanelData::attachNote(int pid){
    const QString action="note:"+QUuid::createUuid().toString(QUuid::WithoutBraces);
    QTimer::singleShot(0,this,[this,pid,action]{
        if(pid<2){actionError(action,tr("Ungültiges Notes-Fenster."));return;}
        runHelper({"--topbar-note",QString::number(pid)},action);
    });
    return action;
}
QString PanelData::ask(const QString &prompt,const QString &file,const QVariantMap &note){
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
    if(!file.isEmpty()){
        const QFileInfo info(file);
        if(file.size()>4096 || file.contains(QChar::Null) || !info.isAbsolute() || !info.isFile() || !info.isReadable()){
            return reject(tr("Die angehängte Datei ist nicht mehr lesbar."));
        }
        request["file"]=file;
    }
    const auto payload=QJsonDocument(request).toJson(QJsonDocument::Compact);
    QTimer::singleShot(0,this,[this,action,payload]{runHelper({"--ask"},action,0,payload);});
    return action;
}
void PanelData::runHelper(const QStringList &arguments,const QString &action,int value,const QByteArray &input){
    const bool mutating=action=="volume" || action=="brightness" || action=="mute";
    if(mutating && controlBusy())return;
    if(m_helper.isEmpty()){actionError(action,tr("Lumen ist nicht vollständig installiert."));return;}
    m_actionError.clear();emit errorChanged();
    if(mutating && m_read.state()!=QProcess::NotRunning){m_ignoreRead=true;m_timeout.stop();m_read.kill();}
    auto command=new QProcess(this);auto timeout=new QTimer(command);timeout->setSingleShot(true);timeout->setInterval(action.startsWith("note:")?45000:15000);
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
        if(failure.isEmpty() && mutating && !result["system"].isObject())failure=tr("Ungültige Systemdaten.");
        if(failure.isEmpty() && action.startsWith("note:") && !result["note"].isObject())failure=tr("Ungültige Notes-Auswahl.");
        if(!failure.isEmpty())actionError(action,failure);
        else{
            if(action.startsWith("note:"))emit noteAttached(action,result["note"].toObject().toVariantMap());
            if(mutating){m_snapshot["system"]=result["system"].toObject().toVariantMap();emit changed();}
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
