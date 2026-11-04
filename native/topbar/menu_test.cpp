// SPDX-License-Identifier: MIT
#include <libdbusmenu-glib/server.h>
#include <libdbusmenu-glib/menuitem.h>
#include <gio/gio.h>
#include "appmenu.h"
#include <QApplication>
#include <QTest>
#include <QQuickItem>
#include <QQuickWindow>

class MenuTest:public QObject {
    Q_OBJECT
private slots:
    void endpointValidation() {
        QVERIFY(AppMenu::validEndpoint(":1.54","/MenuBar"));
        QVERIFY(AppMenu::validEndpoint("org.example.Editor","/menus/root"));
        QVERIFY(!AppMenu::validEndpoint("sh -c nope","/MenuBar"));
        QVERIFY(!AppMenu::validEndpoint("org.example.Editor","/../MenuBar"));
        QVERIFY(!AppMenu::validEndpoint("","/MenuBar"));
    }
    void exportedMenuUpdates() {
        auto server=dbusmenu_server_new("/LumenTest");
        auto root=dbusmenu_menuitem_new();
        auto file=dbusmenu_menuitem_new();
        dbusmenu_menuitem_property_set(file,DBUSMENU_MENUITEM_PROP_LABEL,"_Datei");
        dbusmenu_menuitem_property_set_bool(file,DBUSMENU_MENUITEM_PROP_ENABLED,true);
        dbusmenu_menuitem_child_append(root,file);
        dbusmenu_server_set_root(server,root);
        auto connection=g_bus_get_sync(G_BUS_TYPE_SESSION,nullptr,nullptr);
        AppMenu menu;menu.setEndpoint(QString::fromUtf8(g_dbus_connection_get_unique_name(connection)),"/LumenTest");
        QTRY_COMPARE_WITH_TIMEOUT(menu.entries().size(),1,3000);
        QCOMPARE(menu.entries()[0].toMap()["label"].toString(),QStringLiteral("Datei"));
        dbusmenu_menuitem_property_set_bool(file,DBUSMENU_MENUITEM_PROP_ENABLED,false);
        QTRY_VERIFY_WITH_TIMEOUT(!menu.entries()[0].toMap()["enabled"].toBool(),3000);
        dbusmenu_menuitem_property_set(file,DBUSMENU_MENUITEM_PROP_LABEL,"Rock & Roll__Menu");
        QTRY_COMPARE(menu.entries()[0].toMap()["label"].toString(),QStringLiteral("Rock & Roll_Menu"));
        bool activated=false;
        g_signal_connect(file,DBUSMENU_MENUITEM_SIGNAL_ITEM_ACTIVATED,G_CALLBACK(+[](DbusmenuMenuitem*,guint,gpointer value){*static_cast<bool*>(value)=true;}),&activated);
        QQuickWindow window;QQuickItem anchor(window.contentItem());
        menu.show(0,&anchor);QTest::qWait(30);QVERIFY(!activated);
        dbusmenu_menuitem_property_set_bool(file,DBUSMENU_MENUITEM_PROP_ENABLED,true);
        QTRY_VERIFY(menu.entries()[0].toMap()["enabled"].toBool());menu.show(0,&anchor);
        QTRY_VERIFY_WITH_TIMEOUT(activated,3000);
        menu.setEndpoint("","");QVERIFY(menu.entries().isEmpty());
        g_object_unref(connection);g_object_unref(file);g_object_unref(root);g_object_unref(server);
    }
};
QTEST_MAIN(MenuTest)
#include "menu_test.moc"
