// SPDX-License-Identifier: MIT
#include "paneldata.h"
#include <QApplication>
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

PanelData::PanelData(QObject *parent):QObject(parent) {
    auto bus=QDBusConnection::sessionBus();
    bus.registerService("org.kde.kappmenuview");
    auto viewWatcher=new QDBusServiceWatcher("org.kde.kappmenuview",bus,QDBusServiceWatcher::WatchForUnregistration,this);
    connect(viewWatcher,&QDBusServiceWatcher::serviceUnregistered,this,[]{QDBusConnection::sessionBus().registerService("org.kde.kappmenuview");});
    const QString directory=qEnvironmentVariable("LUMEN_BIN_DIR",QCoreApplication::applicationDirPath());
    const QString local=QDir(directory).filePath("lumen-panel");
    m_helper=QFileInfo(local).isExecutable()?local:QStandardPaths::findExecutable("lumen-panel");
    const auto p=QApplication::palette();
    m_snapshot={{"apps",QVariantList{}},{"system",QVariantMap{}},{"operations",QVariantMap{}},
        {"palette",QVariantMap{{"window",p.color(QPalette::Window).name()},{"base",p.color(QPalette::Base).name()},
        {"text",p.color(QPalette::WindowText).name()},{"muted",p.color(QPalette::PlaceholderText).name()},
        {"border",p.color(QPalette::Mid).name()},{"alternate",p.color(QPalette::AlternateBase).name()},
        {"accent",p.color(QPalette::Highlight).name()},{"onAccent",p.color(QPalette::HighlightedText).name()}}}};
    m_read.setProcessChannelMode(QProcess::SeparateChannels);m_timeout.setSingleShot(true);m_timeout.setInterval(15000);
    connect(&m_timeout,&QTimer::timeout,this,[this]{m_read.kill();fail(tr("Die Systemdaten antworten gerade nicht."));});
    connect(&m_read,&QProcess::readyReadStandardError,this,[this]{m_read.readAllStandardError();});
    connect(&m_read,&QProcess::readyReadStandardOutput,this,[this]{if(m_read.bytesAvailable()>1024*1024){m_read.kill();fail(tr("Ungültige Systemdaten."));}});
    connect(&m_read,&QProcess::errorOccurred,this,[this](QProcess::ProcessError e){if(e==QProcess::FailedToStart){m_timeout.stop();fail(tr("Der Lumen-Leistenhelfer konnte nicht gestartet werden."));}});
    connect(&m_read,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus status){
        m_timeout.stop();const auto bytes=m_read.readAllStandardOutput();
        if(code || status!=QProcess::NormalExit || bytes.size()>1024*1024){fail(tr("Die Systemdaten konnten nicht geladen werden."));return;}
        QJsonParseError error;const auto document=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !document.isObject() || document["version"].toInt()!=1 || !document["apps"].isArray()){
            fail(tr("Ungültige Systemdaten."));return;
        }
        m_snapshot=document.object().toVariantMap();applyPalette(m_snapshot["palette"].toMap());
        if(!m_error.isEmpty()){m_error.clear();emit errorChanged();}emit changed();
    });
    m_poll.setInterval(10000);connect(&m_poll,&QTimer::timeout,this,&PanelData::refresh);m_poll.start();
    QTimer::singleShot(0,this,&PanelData::refresh);
}
void PanelData::fail(const QString &message){if(message!=m_error){m_error=message;emit errorChanged();}}
void PanelData::refresh(){if(m_read.state()!=QProcess::NotRunning)return;if(m_helper.isEmpty()){fail(tr("Lumen ist nicht vollständig installiert."));return;}m_read.start(m_helper,{"--bar-snapshot"});m_timeout.start();}
void PanelData::applyPalette(const QVariantMap &colors){
    const QList<QPair<QPalette::ColorRole,QString>> roles={{QPalette::Window,"window"},{QPalette::Base,"base"},
        {QPalette::WindowText,"text"},{QPalette::Text,"text"},{QPalette::ButtonText,"text"},{QPalette::Button,"window"},
        {QPalette::Mid,"border"},{QPalette::Midlight,"alternate"},{QPalette::Highlight,"accent"},
        {QPalette::HighlightedText,"onAccent"},{QPalette::PlaceholderText,"muted"},{QPalette::AlternateBase,"alternate"}};
    auto p=QApplication::palette();for(const auto &[role,key]:roles){const QColor color(colors[key].toString());if(color.isValid())p.setColor(role,color);}QApplication::setPalette(p);
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
void PanelData::control(const QString &action,int value){
    static const QStringList actions={"volume","brightness","mute","network","audio","display","appearance","hardware","desktop-settings","lock","search"};
    if(!actions.contains(action))return;
    if(action=="volume" || action=="brightness"){if(value<0 || value>100)return;start({"--control",action,"--value",QString::number(value)});}
    else start({"--control",action});
    QTimer::singleShot(400,this,&PanelData::refresh);
}
void PanelData::context(const QString &app,const QString &title,int pid){
    if((app=="Lumen Reader" || app=="Reader") && pid>1){start({"--topbar-reader",QString::number(pid)});return;}
    static const QStringList browsers={"Chromium","Google Chrome","Brave","Mozilla Firefox","Microsoft Edge","Vivaldi"};
    if(browsers.contains(app) && title.size()<=4000){const auto data=QJsonDocument(QJsonObject{{"title",title},{"app",app}}).toJson(QJsonDocument::Compact).toBase64();start({"--topbar-page",QString::fromLatin1(data)});}
}
void PanelData::inputMask(QQuickWindow *window,const QVariantList &rectangles){
    if(!window)return;
    QRegion mask;
    for(const auto &value:rectangles){const auto r=value.toRect();if(r.isValid())mask+=r;}
    window->setMask(mask);
}
void PanelData::ShowApps(){auto screen=QGuiApplication::screenAt(QCursor::pos());if(!screen)screen=QGuiApplication::primaryScreen();if(screen)emit showAppsRequested(screen->name());}
