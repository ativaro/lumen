// SPDX-License-Identifier: MIT
#include <libdbusmenu-glib/client.h>
#include <libdbusmenu-glib/menuitem.h>
#include "appmenu.h"
#include <QAction>
#include <QApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusReply>
#include <QDBusServiceWatcher>
#include <QIcon>
#include <QMenu>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QTimer>

namespace {
QString text(DbusmenuMenuitem *item,const char *key) {
    const char *value=dbusmenu_menuitem_property_get(item,key);
    return value ? QString::fromUtf8(value) : QString();
}
bool flag(DbusmenuMenuitem *item,const char *key,bool fallback=true) {
    return dbusmenu_menuitem_property_exist(item,key) ? dbusmenu_menuitem_property_get_bool(item,key) : fallback;
}
QString label(DbusmenuMenuitem *item,bool mnemonic=true) {
    const QString source=text(item,DBUSMENU_MENUITEM_PROP_LABEL);
    QString result;
    for(qsizetype i=0;i<source.size();++i){
        const QChar c=source[i];
        if(c=='_'){
            if(i+1<source.size() && source[i+1]=='_'){result+='_' ;++i;}
            else if(mnemonic && i+1<source.size())result+='&';
        }else if(c=='&' && mnemonic)result+="&&";
        else result+=c;
    }
    return result;
}
QString shortcut(DbusmenuMenuitem *item) {
    auto value=dbusmenu_menuitem_property_get_variant(item,DBUSMENU_MENUITEM_PROP_SHORTCUT);
    if(!value || !g_variant_is_of_type(value,G_VARIANT_TYPE("aas")) || !g_variant_n_children(value))return {};
    auto sequence=g_variant_get_child_value(value,0);QStringList keys;
    for(gsize i=0;i<g_variant_n_children(sequence) && i<8;++i){
        auto part=g_variant_get_child_value(sequence,i);QString key=QString::fromUtf8(g_variant_get_string(part,nullptr));g_variant_unref(part);
        if(key=="Control")key="Ctrl";else if(key=="Super")key="Meta";
        keys.append(key);
    }
    g_variant_unref(sequence);
    return QKeySequence::fromString(keys.join('+'),QKeySequence::PortableText).toString(QKeySequence::NativeText);
}
}

AppMenu::AppMenu(QObject *parent):QObject(parent) {}
AppMenu::~AppMenu() { close();releaseClient(); }

void AppMenu::releaseClient() {
    for(auto item:m_watched){g_signal_handlers_disconnect_by_data(item,this);g_object_set_data(G_OBJECT(item),"lumen-topbar-watched",nullptr);g_object_unref(item);}
    m_watched.clear();
    if(m_client){g_signal_handlers_disconnect_by_data(m_client,this);g_object_unref(m_client);m_client=nullptr;}
}

bool AppMenu::validEndpoint(const QString &service,const QString &path) {
    static const QRegularExpression bus(QStringLiteral(R"(^(?::[0-9]+\.[0-9]+|[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)+)$)"));
    static const QRegularExpression object(QStringLiteral(R"(^/(?:[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*)?$)"));
    return service.size()<=255 && path.size()<=4096 && bus.match(service).hasMatch() && object.match(path).hasMatch();
}

void AppMenu::setEndpoint(const QString &service,const QString &path) {
    if(service==m_service && path==m_path)return;
    close();++m_generation;
    releaseClient();
    if(m_ownerWatcher){m_ownerWatcher->deleteLater();m_ownerWatcher=nullptr;}
    m_service=service;m_path=path;m_entries.clear();emit entriesChanged();
    if(!validEndpoint(service,path))return;
    auto bus=QDBusConnection::sessionBus();
    const auto owner=bus.interface()->serviceOwner(service);
    if(!owner.isValid() || owner.value().isEmpty())return;
    m_ownerWatcher=new QDBusServiceWatcher(service,bus,QDBusServiceWatcher::WatchForOwnerChange,this);
    const auto generation=m_generation;
    connect(m_ownerWatcher,&QDBusServiceWatcher::serviceOwnerChanged,this,[this,service,path,generation]{if(generation==m_generation){m_service.clear();setEndpoint(service,path);}});
    m_client=dbusmenu_client_new(owner.value().toUtf8().constData(),path.toUtf8().constData());
    g_signal_connect(m_client,DBUSMENU_CLIENT_SIGNAL_ROOT_CHANGED,G_CALLBACK(+[](DbusmenuClient *,DbusmenuMenuitem *,gpointer p){static_cast<AppMenu*>(p)->refresh();}),this);
    g_signal_connect(m_client,DBUSMENU_CLIENT_SIGNAL_LAYOUT_UPDATED,G_CALLBACK(+[](DbusmenuClient *,gpointer p){static_cast<AppMenu*>(p)->refresh();}),this);
    g_signal_connect(m_client,DBUSMENU_CLIENT_SIGNAL_NEW_MENUITEM,G_CALLBACK(+[](DbusmenuClient *,DbusmenuMenuitem *item,gpointer p){static_cast<AppMenu*>(p)->watch(item);}),this);
    refresh();
}

void AppMenu::watch(DbusmenuMenuitem *item) {
    if(g_object_get_data(G_OBJECT(item),"lumen-topbar-watched"))return;
    g_object_set_data(G_OBJECT(item),"lumen-topbar-watched",this);
    m_watched.append(DBUSMENU_MENUITEM(g_object_ref(item)));
    g_signal_connect(item,DBUSMENU_MENUITEM_SIGNAL_PROPERTY_CHANGED,G_CALLBACK(+[](DbusmenuMenuitem *,gchar *,GVariant *,gpointer p){auto self=static_cast<AppMenu*>(p);QTimer::singleShot(0,self,[self]{self->refresh();});}),this);
}

void AppMenu::refresh() {
    if(!m_client)return;
    QVariantList entries;
    auto root=dbusmenu_client_get_root(m_client);
    if(root)watch(root);
    int count=0;
    for(auto child=root ? dbusmenu_menuitem_get_children(root):nullptr;child && count<4096;child=child->next,++count){
        auto item=DBUSMENU_MENUITEM(child->data);
        watch(item);
        if(!flag(item,DBUSMENU_MENUITEM_PROP_VISIBLE) || text(item,DBUSMENU_MENUITEM_PROP_TYPE)==QStringLiteral("separator"))continue;
        entries.append(QVariantMap{{"id",dbusmenu_menuitem_get_id(item)},{"label",label(item,false)},{"enabled",flag(item,DBUSMENU_MENUITEM_PROP_ENABLED)}});
    }
    if(entries!=m_entries){m_entries=entries;emit entriesChanged();}
    if(m_popup && m_current)populate(m_popup,m_current);
    if(m_pendingAnchor && root){const auto anchor=m_pendingAnchor;m_pendingAnchor=nullptr;popup(root,anchor);}
}

void AppMenu::populate(QMenu *menu,DbusmenuMenuitem *item,int depth) {
    if(depth>24)return;
    QList<DbusmenuMenuitem*> nodes;
    int count=0;
    for(auto child=dbusmenu_menuitem_get_children(item);child && count<4096;child=child->next,++count){
        auto node=DBUSMENU_MENUITEM(child->data);
        if(flag(node,DBUSMENU_MENUITEM_PROP_VISIBLE))nodes.append(node);
    }
    auto actions=menu->actions();
    bool same=actions.size()==nodes.size();
    for(int i=0;same && i<nodes.size();++i){
        const auto node=nodes[i];
        const bool submenu=dbusmenu_menuitem_get_children(node) || text(node,DBUSMENU_MENUITEM_PROP_CHILD_DISPLAY)==QStringLiteral("submenu");
        same=actions[i]->data().value<quintptr>()==reinterpret_cast<quintptr>(node)
            && actions[i]->isSeparator()==(text(node,DBUSMENU_MENUITEM_PROP_TYPE)==QStringLiteral("separator"))
            && bool(actions[i]->menu())==submenu;
    }
    // Property updates must keep the user's current selection and popup grab.
    if(!same){
        qDeleteAll(menu->findChildren<QMenu*>(QString(),Qt::FindDirectChildrenOnly));menu->clear();
        for(auto node:nodes){
            auto action=menu->addAction(QString());action->setData(QVariant::fromValue(reinterpret_cast<quintptr>(node)));
            if(text(node,DBUSMENU_MENUITEM_PROP_TYPE)==QStringLiteral("separator")){action->setSeparator(true);continue;}
            g_object_ref(node);connect(action,&QObject::destroyed,this,[node]{g_object_unref(node);});
            if(dbusmenu_menuitem_get_children(node) || text(node,DBUSMENU_MENUITEM_PROP_CHILD_DISPLAY)==QStringLiteral("submenu")){
                auto sub=new QMenu(menu);action->setMenu(sub);
                connect(sub,&QMenu::aboutToShow,this,[this,sub,node,depth]{dbusmenu_menuitem_send_about_to_show(node,nullptr,nullptr);populate(sub,node,depth+1);});
            }else{
                const auto generation=m_generation;
                connect(action,&QAction::triggered,this,[this,node,generation]{if(generation==m_generation && flag(node,DBUSMENU_MENUITEM_PROP_ENABLED) && flag(node,DBUSMENU_MENUITEM_PROP_VISIBLE))dbusmenu_menuitem_handle_event(node,DBUSMENU_MENUITEM_EVENT_ACTIVATED,g_variant_new_int32(0),0);});
            }
        }
        actions=menu->actions();
    }
    for(int i=0;i<nodes.size();++i){
        auto node=nodes[i];auto action=actions[i];if(action->isSeparator())continue;
        const auto key=shortcut(node);action->setText(label(node)+(key.isEmpty()?QString():"\t"+key));
        action->setIcon(QIcon::fromTheme(text(node,DBUSMENU_MENUITEM_PROP_ICON_NAME)));
        action->setEnabled(flag(node,DBUSMENU_MENUITEM_PROP_ENABLED));
        const auto toggle=text(node,DBUSMENU_MENUITEM_PROP_TOGGLE_TYPE);action->setCheckable(!toggle.isEmpty());
        if(!toggle.isEmpty())action->setChecked(dbusmenu_menuitem_property_get_int(node,DBUSMENU_MENUITEM_PROP_TOGGLE_STATE)==1);
        if(action->menu())populate(action->menu(),node,depth+1);
    }
}

void AppMenu::popup(DbusmenuMenuitem *item,QQuickItem *anchor) {
    if(!item || !anchor || !anchor->window() || !flag(item,DBUSMENU_MENUITEM_PROP_ENABLED))return;
    close();m_current=DBUSMENU_MENUITEM(g_object_ref(item));
    auto menu=new QMenu;menu->setPalette(QApplication::palette());m_popup=menu;
    connect(menu,&QMenu::aboutToHide,this,[this,menu]{if(m_popup==menu){m_popup=nullptr;if(m_current){g_object_unref(m_current);m_current=nullptr;}emit openedChanged();}menu->deleteLater();});
    populate(menu,item);dbusmenu_menuitem_send_about_to_show(item,nullptr,nullptr);
    menu->winId();menu->windowHandle()->setTransientParent(anchor->window());
    emit openedChanged();menu->popup(anchor->mapToGlobal(QPointF(0,anchor->height())).toPoint());
}

void AppMenu::show(int index,QQuickItem *anchor) {
    if(!m_client || index<0 || index>=m_entries.size())return;
    const int id=m_entries[index].toMap()["id"].toInt();
    auto root=dbusmenu_client_get_root(m_client);
    for(auto child=root ? dbusmenu_menuitem_get_children(root):nullptr;child;child=child->next){auto item=DBUSMENU_MENUITEM(child->data);if(dbusmenu_menuitem_get_id(item)==id){
        if(!flag(item,DBUSMENU_MENUITEM_PROP_ENABLED) || !flag(item,DBUSMENU_MENUITEM_PROP_VISIBLE))return;
        if(!dbusmenu_menuitem_get_children(item) && text(item,DBUSMENU_MENUITEM_PROP_CHILD_DISPLAY)!=QStringLiteral("submenu"))
            dbusmenu_menuitem_handle_event(item,DBUSMENU_MENUITEM_EVENT_ACTIVATED,g_variant_new_int32(0),0);
        else popup(item,anchor);
        return;
    }}
}
void AppMenu::showRoot(QQuickItem *anchor) {if(m_client){auto root=dbusmenu_client_get_root(m_client);if(root)popup(root,anchor);else m_pendingAnchor=anchor;}}
void AppMenu::close() {
    m_pendingAnchor=nullptr;
    if(m_popup)m_popup->close();
    if(m_current){g_object_unref(m_current);m_current=nullptr;}
}
