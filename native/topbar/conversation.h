// SPDX-License-Identifier: MIT
#pragma once
#include <QObject>
#include <QProcess>
#include <QVariantMap>
#include <QSet>
#include <QTimer>

class Conversation:public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap state READ state NOTIFY changed)
public:
    explicit Conversation(QString helper,QObject *parent=nullptr);
    ~Conversation() override;
    QVariantMap state() const {return m_state;}
    Q_INVOKABLE void call(const QString &method,const QVariantList &arguments={});
    void submit(const QString &prompt,const QVariantMap &note,const QString &identity);
signals:
    void changed();
    void finished(const QString &identity,const QString &error);
private:
    void send(const QString &method,const QVariantList &arguments,const QString &identity={});
    void fail();
    QString m_helper;
    QProcess m_process;
    QTimer m_startTimer;
    QByteArray m_pending;
    QVariantMap m_state;
    QSet<QString> m_requests;
};
