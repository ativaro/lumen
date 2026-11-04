// SPDX-License-Identifier: MIT
#include "tray.h"
#include <QCoreApplication>
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusObjectPath>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QDBusVariant>
#include <QIcon>
#include <QImage>
#include <QPixmap>
#include <QQuickItem>

namespace {
constexpr auto watcher="org.kde.StatusNotifierWatcher";
constexpr auto watcherPath="/StatusNotifierWatcher";
constexpr auto itemInterface="org.kde.StatusNotifierItem";
QIcon itemIcon(const QVariantMap &properties) {
    const QString name=properties.value("Status")==QStringLiteral("NeedsAttention") && !properties.value("AttentionIconName").toString().isEmpty()
        ?properties.value("AttentionIconName").toString():properties.value("IconName").toString();
    if(!name.isEmpty() && !name.contains("://")){const auto icon=QIcon::fromTheme(name);if(!icon.isNull())return icon;}
    if(properties.value("IconPixmap").metaType()!=QMetaType::fromType<QDBusArgument>())return QIcon::fromTheme("application-x-executable");
    const auto argument=qvariant_cast<QDBusArgument>(properties.value("IconPixmap"));
    if(argument.currentSignature()!=QStringLiteral("a(iiay)"))return QIcon::fromTheme("application-x-executable");
    QImage image;int best=100000;
    argument.beginArray();
    while(!argument.atEnd()){
        int width=0,height=0;QByteArray bytes;
        argument.beginStructure();argument>>width>>height>>bytes;argument.endStructure();
        if(width<=0 || height<=0 || width>512 || height>512 || bytes.size()!=qint64(width)*height*4)continue;
        const int distance=qAbs(width-32)+qAbs(height-32);
        if(distance>=best)continue;
        best=distance;image=QImage(width,height,QImage::Format_ARGB32);
        for(int y=0;y<height;y++){auto output=reinterpret_cast<QRgb*>(image.scanLine(y));for(int x=0;x<width;x++){
            const auto p=reinterpret_cast<const uchar*>(bytes.constData())+(y*width+x)*4;
            output[x]=qRgba(p[1],p[2],p[3],p[0]);
        }}
    }
    return image.isNull()?QIcon::fromTheme("application-x-executable"):QIcon(QPixmap::fromImage(image));
}
}

Tray::Tray(QObject *parent):QObject(parent),m_menu(this) {
    auto bus=QDBusConnection::sessionBus();m_host="org.kde.StatusNotifierHost.lumen.p"+QString::number(QCoreApplication::applicationPid());
    bus.registerService(m_host);m_reload.setSingleShot(true);m_reload.setInterval(100);
    connect(&m_reload,&QTimer::timeout,this,&Tray::reload);
    connect(&m_menu,&AppMenu::openedChanged,this,&Tray::openedChanged);
    auto availability=new QDBusServiceWatcher(watcher,bus,QDBusServiceWatcher::WatchForOwnerChange,this);
    connect(availability,&QDBusServiceWatcher::serviceOwnerChanged,this,[this]{m_reload.start();});
    bus.connect(watcher,watcherPath,watcher,"StatusNotifierItemRegistered",this,SLOT(itemChanged(QDBusMessage)));
    bus.connect(watcher,watcherPath,watcher,"StatusNotifierItemUnregistered",this,SLOT(itemChanged(QDBusMessage)));
    QTimer::singleShot(0,this,&Tray::reload);
}
QPair<QString,QString> Tray::endpoint(const QString &identity){
    const auto slash=identity.indexOf('/');
    return slash<0?qMakePair(identity,QStringLiteral("/StatusNotifierItem")):qMakePair(identity.left(slash),identity.mid(slash));
}
QVariantList Tray::items() const {
    QVariantList result;for(const auto &key:m_order)if(m_rows.contains(key))result.append(m_rows.value(key));return result;
}
void Tray::itemChanged(const QDBusMessage &){m_reload.start();}
void Tray::reload(){
    const auto generation=++m_generation;
    auto registerHost=QDBusMessage::createMethodCall(watcher,watcherPath,watcher,"RegisterStatusNotifierHost");registerHost<<m_host;
    QDBusConnection::sessionBus().asyncCall(registerHost,2000);
    auto message=QDBusMessage::createMethodCall(watcher,watcherPath,"org.freedesktop.DBus.Properties","Get");
    message<<QString(watcher)<<QStringLiteral("RegisteredStatusNotifierItems");
    auto pending=new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message,2000),this);
    connect(pending,&QDBusPendingCallWatcher::finished,this,[this,generation](QDBusPendingCallWatcher *call){
        QDBusPendingReply<QDBusVariant> reply=*call;call->deleteLater();if(generation!=m_generation)return;
        const auto previous=m_order;m_order.clear();
        if(!reply.isError()){
            const auto value=reply.value().variant();const auto values=value.canConvert<QStringList>()?value.toStringList():qdbus_cast<QStringList>(value);
            for(const auto &identity:values){const auto [service,path]=endpoint(identity);if(AppMenu::validEndpoint(service,path) && !m_order.contains(identity))m_order.append(identity);}
        }
        for(const auto &key:previous)if(!m_order.contains(key)){
            const auto [service,path]=endpoint(key);auto bus=QDBusConnection::sessionBus();
            bus.disconnect(service,path,itemInterface,QString(),this,SLOT(itemChanged(QDBusMessage)));m_rows.remove(key);m_menu.close();
        }
        emit changed();
        for(const auto &identity:m_order){
            const auto [service,path]=endpoint(identity);
            if(!previous.contains(identity))QDBusConnection::sessionBus().connect(service,path,itemInterface,QString(),this,SLOT(itemChanged(QDBusMessage)));
            fetch(identity,generation);
        }
    });
}
void Tray::fetch(const QString &identity,quint64 generation){
    const auto [service,path]=endpoint(identity);
    auto message=QDBusMessage::createMethodCall(service,path,"org.freedesktop.DBus.Properties","GetAll");message<<QString(itemInterface);
    auto pending=new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message,2000),this);
    connect(pending,&QDBusPendingCallWatcher::finished,this,[this,identity,service,path,generation](QDBusPendingCallWatcher *call){
        QDBusPendingReply<QVariantMap> reply=*call;call->deleteLater();
        if(generation!=m_generation || !m_order.contains(identity))return;
        if(reply.isError()){m_rows.remove(identity);emit changed();return;}
        const auto properties=reply.value();
        m_rows[identity]={{"identity",identity},{"service",service},{"path",path},
            {"title",properties.value("Title",properties.value("Id")).toString().left(512)},
            {"status",properties.value("Status").toString()},{"icon",QVariant::fromValue(itemIcon(properties))},
            {"isMenu",properties.value("ItemIsMenu").toBool()},{"menu",qvariant_cast<QDBusObjectPath>(properties.value("Menu")).path()}};
        emit changed();
    });
}
void Tray::activate(const QString &identity,QQuickItem *anchor,int button){
    if(!m_rows.contains(identity) || !anchor)return;
    const auto row=m_rows.value(identity);const auto service=row["service"].toString(),path=row["path"].toString();
    const auto point=anchor->mapToGlobal(QPointF(anchor->width()/2,anchor->height()/2)).toPoint();
    if((button==3 || row["isMenu"].toBool()) && AppMenu::validEndpoint(service,row["menu"].toString())){
        m_menu.setEndpoint(service,row["menu"].toString());m_menu.showRoot(anchor);return;
    }
    auto message=QDBusMessage::createMethodCall(service,path,itemInterface,button==2?"SecondaryActivate":button==3?"ContextMenu":"Activate");message<<point.x()<<point.y();
    QDBusConnection::sessionBus().asyncCall(message,2000);
}
