// SPDX-License-Identifier: MIT
#pragma once
#include <QObject>
#include <QProcess>
#include <QPointer>
#include <QVariantMap>
#include <QTimer>
#include <QFileSystemWatcher>
#include <QMap>
#include <QSet>
#include <memory>
#include "conversation.h"

class QQuickWindow;
class QQuickItem;
class QLabel;
class PanelData:public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface","org.lumen.Topbar")
    Q_PROPERTY(QVariantMap snapshot READ snapshot NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(bool controlBusy READ controlBusy NOTIFY controlBusyChanged)
    Q_PROPERTY(QString layout READ layout NOTIFY layoutChanged)
    Q_PROPERTY(QVariantMap details READ details NOTIFY detailsChanged)
    Q_PROPERTY(QVariantList players READ players NOTIFY playersChanged)
    Q_PROPERTY(QStringList pinnedApps READ pinnedApps WRITE setPinnedApps NOTIFY pinnedAppsChanged)
    Q_PROPERTY(QString userName READ userName CONSTANT)
    Q_PROPERTY(Conversation* conversation READ conversation CONSTANT)
public:
    explicit PanelData(QObject *parent=nullptr);
    ~PanelData() override;
    QVariantMap snapshot() const {return m_snapshot;}
    QString error() const {return m_actionError.isEmpty()?m_error:m_actionError;}
    bool controlBusy() const {return m_control && m_control->state()!=QProcess::NotRunning;}
    QString layout() const {return m_layout;}
    QVariantMap details() const {return m_details;}
    QVariantList players() const;
    QStringList pinnedApps() const;
    void setPinnedApps(QStringList apps);
    QString userName() const;
    Conversation *conversation() const {return m_conversation;}
    Q_INVOKABLE void mediaAction(const QString &service,const QString &action);
    Q_INVOKABLE void inspect(const QString &topic);
    Q_INVOKABLE void systemAction(const QString &topic,const QString &action,const QString &target={},int value=0);
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void launch(const QString &action,const QString &value={});
    Q_INVOKABLE void control(const QString &action,int value=0);
    Q_INVOKABLE QString ask(const QString &prompt,const QVariantMap &note={});
    Q_INVOKABLE QString attachNote(int pid);
    Q_INVOKABLE void tooltip(QQuickItem *anchor,const QString &text);
    Q_INVOKABLE void context(const QString &app,const QString &title,int pid);
    Q_INVOKABLE void inputMask(QQuickWindow *window,const QVariantList &rectangles,bool popupOpen=false);
public slots:
    Q_SCRIPTABLE void ShowApps();
    void refreshMedia();
    void mediaPropertiesChanged(const QString &interface,const QVariantMap &changed,const QStringList &invalidated);
    void mediaOwnerChanged(const QString &name,const QString &oldOwner,const QString &newOwner);
signals:
    void pinnedAppsChanged();
    void playersChanged();
    void controlBusyChanged();
    void controlFinished(const QString &action,int value);
    void controlFailed(const QString &action);
    void changed();
    void errorChanged();
    void showAppsRequested(const QString &screen);
    void layoutChanged();
    void detailsChanged();
    void noteAttached(const QString &action,const QVariantMap &note);
private:
    void runHelper(const QStringList &arguments,const QString &action,int value=0,const QByteArray &input={});
    void start(const QStringList &arguments);
    void fail(const QString &message);
    void actionError(const QString &action,const QString &message);
    void applyPalette(const QVariantMap &colors);
    void readLayout();
    void watchTasks();
    QFileSystemWatcher m_settingsWatcher;
    QFileSystemWatcher m_taskWatcher;
    QTimer m_taskRefresh;
    QString m_taskDirectory;
    QString m_layout="classic";
    QPointer<QQuickItem> m_tooltipOwner;
    std::unique_ptr<QLabel> m_tooltip;
    QMetaObject::Connection m_tooltipDestroyed;
    QString m_helper;
    Conversation *m_conversation=nullptr;
    QProcess m_read;
    QPointer<QProcess> m_control;
    bool m_ignoreRead=false;
    QTimer m_timeout,m_poll;
    QVariantMap m_snapshot;
    QVariantMap m_details;
    QString m_error,m_actionError;
    QMap<QString,QVariantMap> m_players;
    QSet<QString> m_pendingPlayers;
    QMap<QString,quint64> m_playerEpochs;
    bool m_mediaScanning=false,m_mediaAgain=false;
};
