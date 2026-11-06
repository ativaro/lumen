// SPDX-License-Identifier: MIT
#pragma once
#include "appmenu.h"
#include <QDBusMessage>
#include <QHash>
#include <QObject>
#include <QTimer>
#include <QVariantList>

class Tray:public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList items READ items NOTIFY changed)
    Q_PROPERTY(bool opened READ opened NOTIFY openedChanged)
public:
    explicit Tray(QObject *parent=nullptr);
    QVariantList items() const;
    bool opened() const {return m_menu.opened();}
    Q_INVOKABLE void activate(const QString &identity,QQuickItem *anchor,int button=1);
    Q_INVOKABLE void close(){m_menu.close();}
signals:
    void changed();
    void openedChanged();
private slots:
    void reload();
    void itemChanged(const QDBusMessage &message);
private:
    void fetch(const QString &identity,quint64 generation);
    static QPair<QString,QString> endpoint(const QString &identity);
    QString m_host;
    QStringList m_order;
    QHash<QString,QVariantMap> m_rows;
    QTimer m_reload;
    quint64 m_generation=0;
    AppMenu m_menu;
};
