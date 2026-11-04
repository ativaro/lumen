// SPDX-License-Identifier: MIT
#pragma once
#include <QObject>
#include <QProcess>
#include <QPointer>
#include <QVariantMap>
#include <QTimer>

class QQuickWindow;
class PanelData:public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface","org.lumen.Topbar")
    Q_PROPERTY(QVariantMap snapshot READ snapshot NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(bool controlBusy READ controlBusy NOTIFY controlBusyChanged)
public:
    explicit PanelData(QObject *parent=nullptr);
    ~PanelData() override;
    QVariantMap snapshot() const {return m_snapshot;}
    QString error() const {return m_actionError.isEmpty()?m_error:m_actionError;}
    bool controlBusy() const {return m_control && m_control->state()!=QProcess::NotRunning;}
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void launch(const QString &action,const QString &value={});
    Q_INVOKABLE void control(const QString &action,int value=0);
    Q_INVOKABLE void ask(const QString &prompt);
    Q_INVOKABLE void context(const QString &app,const QString &title,int pid);
    Q_INVOKABLE void inputMask(QQuickWindow *window,const QVariantList &rectangles);
public slots:
    Q_SCRIPTABLE void ShowApps();
signals:
    void controlBusyChanged();
    void controlFinished(const QString &action,int value);
    void controlFailed(const QString &action);
    void changed();
    void errorChanged();
    void showAppsRequested(const QString &screen);
private:
    void runHelper(const QStringList &arguments,const QString &action,int value=0,const QByteArray &input={});
    void start(const QStringList &arguments);
    void fail(const QString &message);
    void actionError(const QString &action,const QString &message);
    void applyPalette(const QVariantMap &colors);
    QString m_helper;
    QProcess m_read;
    QPointer<QProcess> m_control;
    bool m_ignoreRead=false;
    QTimer m_timeout,m_poll;
    QVariantMap m_snapshot;
    QString m_error,m_actionError;
};
