// SPDX-License-Identifier: MIT
#include <libdbusmenu-glib/client.h>
#include <libdbusmenu-glib/menuitem.h>
#include "appmenu.h"
#include <QAction>
#include <QApplication>
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
QString label(DbusmenuMenuitem *item) {
    QString value=text(item,DBUSMENU_MENUITEM_PROP_LABEL);
    value.replace('&',QStringLiteral("&&"));
    value.replace('_','&');
    return value;
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
    m_service=service;m_path=path;m_entries.clear();emit entriesChanged();
    if(!validEndpoint(service,path))return;
    m_client=dbusmenu_client_new(service.toUtf8().constData(),path.toUtf8().constData());
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
        if(!flag(item,DBUSMENU_MENUITEM_PROP_VISIBLE))continue;
        entries.append(QVariantMap{{"id",dbusmenu_menuitem_get_id(item)},{"label",label(item).remove('&')},{"enabled",flag(item,DBUSMENU_MENUITEM_PROP_ENABLED)}});
    }
    if(entries!=m_entries){m_entries=entries;emit entriesChanged();}
    if(m_popup && m_current)populate(m_popup,m_current);
}

void AppMenu::populate(QMenu *menu,DbusmenuMenuitem *item,int depth) {
    if(depth>24)return;
    menu->clear();
    int count=0;
    for(auto child=dbusmenu_menuitem_get_children(item);child && count<4096;child=child->next,++count){
        auto node=DBUSMENU_MENUITEM(child->data);
        if(!flag(node,DBUSMENU_MENUITEM_PROP_VISIBLE))continue;
        if(text(node,DBUSMENU_MENUITEM_PROP_TYPE)==QStringLiteral("separator")){menu->addSeparator();continue;}
        auto action=menu->addAction(QIcon::fromTheme(text(node,DBUSMENU_MENUITEM_PROP_ICON_NAME)),label(node));
        action->setEnabled(flag(node,DBUSMENU_MENUITEM_PROP_ENABLED));
        const auto toggle=text(node,DBUSMENU_MENUITEM_PROP_TOGGLE_TYPE);
        if(!toggle.isEmpty()){action->setCheckable(true);action->setChecked(dbusmenu_menuitem_property_get_int(node,DBUSMENU_MENUITEM_PROP_TOGGLE_STATE)==1);}
        g_object_ref(node);
        connect(action,&QObject::destroyed,this,[node]{g_object_unref(node);});
        if(dbusmenu_menuitem_get_children(node) || text(node,DBUSMENU_MENUITEM_PROP_CHILD_DISPLAY)==QStringLiteral("submenu")){
            auto sub=new QMenu(menu);action->setMenu(sub);populate(sub,node,depth+1);
            connect(sub,&QMenu::aboutToShow,this,[this,sub,node,depth]{dbusmenu_menuitem_send_about_to_show(node,nullptr,nullptr);populate(sub,node,depth+1);});
        }else{
            const auto generation=m_generation;
            connect(action,&QAction::triggered,this,[this,node,generation]{if(generation==m_generation && flag(node,DBUSMENU_MENUITEM_PROP_ENABLED) && flag(node,DBUSMENU_MENUITEM_PROP_VISIBLE))dbusmenu_menuitem_handle_event(node,DBUSMENU_MENUITEM_EVENT_ACTIVATED,g_variant_new_int32(0),0);});
        }
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
    for(auto child=root ? dbusmenu_menuitem_get_children(root):nullptr;child;child=child->next){auto item=DBUSMENU_MENUITEM(child->data);if(dbusmenu_menuitem_get_id(item)==id){popup(item,anchor);return;}}
}
void AppMenu::showRoot(QQuickItem *anchor) {if(m_client)popup(dbusmenu_client_get_root(m_client),anchor);}
void AppMenu::close() {
    if(m_popup)m_popup->close();
    if(m_current){g_object_unref(m_current);m_current=nullptr;}
}
