// SPDX-License-Identifier: MIT
#pragma once
#include <QObject>
#include <QProcess>
#include <QVariantMap>
#include <QTimer>

class QQuickWindow;
class PanelData:public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface","org.lumen.Topbar")
    Q_PROPERTY(QVariantMap snapshot READ snapshot NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
public:
    explicit PanelData(QObject *parent=nullptr);
    QVariantMap snapshot() const {return m_snapshot;}
    QString error() const {return m_error;}
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void launch(const QString &action,const QString &value={});
    Q_INVOKABLE void control(const QString &action,int value=0);
    Q_INVOKABLE void context(const QString &app,const QString &title,int pid);
    Q_INVOKABLE void inputMask(QQuickWindow *window,const QVariantList &rectangles);
public slots:
    void ShowApps();
signals:
    void changed();
    void errorChanged();
    void showAppsRequested(const QString &screen);
private:
    void start(const QStringList &arguments);
    void fail(const QString &message);
    void applyPalette(const QVariantMap &colors);
    QString m_helper;
    QProcess m_read;
    QTimer m_timeout,m_poll;
    QVariantMap m_snapshot;
    QString m_error;
};
