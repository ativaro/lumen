// SPDX-License-Identifier: MIT
#pragma once
#include <QObject>
#include <QPointer>
#include <QVariantList>
#include <QVector>

class QQuickItem;
class QMenu;
class QDBusServiceWatcher;
struct _DbusmenuClient;
struct _DbusmenuMenuitem;

class AppMenu : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList entries READ entries NOTIFY entriesChanged)
    Q_PROPERTY(bool opened READ opened NOTIFY openedChanged)
public:
    explicit AppMenu(QObject *parent=nullptr);
    ~AppMenu() override;
    QVariantList entries() const { return m_entries; }
    bool opened() const { return !m_popup.isNull(); }
    Q_INVOKABLE void setEndpoint(const QString &service, const QString &path);
    Q_INVOKABLE void show(int index, QQuickItem *anchor);
    Q_INVOKABLE void showRoot(QQuickItem *anchor);
    Q_INVOKABLE void close();
    static bool validEndpoint(const QString &service, const QString &path);
signals:
    void entriesChanged();
    void openedChanged();
private:
    void refresh();
    void releaseClient();
    void attach(const QString &owner, const QString &service, const QString &path, quint64 generation);
    void watch(_DbusmenuMenuitem *item);
    void populate(QMenu *menu, _DbusmenuMenuitem *item, int depth=0);
    void popup(_DbusmenuMenuitem *item, QQuickItem *anchor);
    _DbusmenuClient *m_client=nullptr;
    _DbusmenuMenuitem *m_current=nullptr;
    QString m_service, m_path;
    QVariantList m_entries;
    QPointer<QMenu> m_popup;
    quint64 m_generation=0;
    QVector<_DbusmenuMenuitem *> m_watched;
    QPointer<QQuickItem> m_pendingAnchor;
    QDBusServiceWatcher *m_ownerWatcher=nullptr;
};
