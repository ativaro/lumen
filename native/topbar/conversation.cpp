// SPDX-License-Identifier: MIT
#include "conversation.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QGuiApplication>
#include <QClipboard>

Conversation::Conversation(QString helper,QObject *parent):QObject(parent),m_helper(std::move(helper)) {
    m_startTimer.setSingleShot(true);m_startTimer.setInterval(15000);
    connect(&m_startTimer,&QTimer::timeout,this,[this]{m_process.kill();fail();});
    connect(&m_process,&QProcess::started,this,[this]{m_process.write(m_pending);m_pending.clear();});
    connect(&m_process,&QProcess::readyReadStandardError,this,[this]{m_process.readAllStandardError();});
    connect(&m_process,&QProcess::readyReadStandardOutput,this,[this]{
        while(m_process.canReadLine()){
            const auto doc=QJsonDocument::fromJson(m_process.readLine());
            if(!doc.isObject()){fail();continue;}
            const auto value=doc.object();
            if(value.value("clipboard").isString())QGuiApplication::clipboard()->setText(value.value("clipboard").toString());
            if(value.value("state").isObject()){
                m_startTimer.stop();
                auto state=value.value("state").toObject().toVariantMap();
                if(!state.contains("labels"))state["labels"]=m_state.value("labels");
                m_state=state;emit changed();
            }
            if(value.value("id").isString()){
                const auto identity=value.value("id").toString();m_requests.remove(identity);
                emit finished(identity,value.value("error").toString());
            }
        }
    });
    connect(&m_process,&QProcess::errorOccurred,this,[this]{fail();});
    connect(&m_process,&QProcess::finished,this,[this]{fail();});
}
Conversation::~Conversation(){
    if(m_process.state()!=QProcess::NotRunning){
        m_process.write("{\"method\":\"close\",\"args\":[]}\n");m_process.closeWriteChannel();
        if(!m_process.waitForFinished(5000)){m_process.terminate();m_process.waitForFinished(1000);}
    }
}
void Conversation::fail(){
    m_startTimer.stop();
    m_state["error"]=tr("Das Gespräch ist gerade nicht erreichbar. Bitte erneut versuchen.");m_state["busy"]=false;
    emit changed();const auto requests=m_requests;m_requests.clear();m_pending.clear();
    for(const auto &identity:requests)emit finished(identity,m_state.value("error").toString());
}
void Conversation::send(const QString &method,const QVariantList &arguments,const QString &identity){
    if(!identity.isEmpty())m_requests.insert(identity);
    const auto line=QJsonDocument(QJsonObject{{"method",method},{"args",QJsonArray::fromVariantList(arguments)},{"id",identity}}).toJson(QJsonDocument::Compact)+'\n';
    if(m_process.state()==QProcess::Running){m_process.write(line);return;}
    m_pending+=line;
    if(m_process.state()==QProcess::Starting)return;
    if(m_helper.isEmpty()){fail();return;}
    m_startTimer.start();m_process.start(m_helper,{"--conversation"});
}
void Conversation::call(const QString &method,const QVariantList &arguments){
    if((method=="hidden" || method=="draft") && m_process.state()==QProcess::NotRunning)return;
    send(method,arguments);
}
void Conversation::submit(const QString &prompt,const QVariantMap &note,const QString &identity){send("submit",{prompt,note},identity);}
