// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QtWidgets>
#include <functional>
using BackupRequest =
    std::function<void(QJsonObject, std::function<void(QJsonValue)>,
                       std::function<void(QString)>)>;

bool backupKeyDestinationAllowed(const QString &file,
                                 const QString &destination);

class NetworkPicker : public QWidget {
  Q_OBJECT
public:
  NetworkPicker(bool english, bool writable, BackupRequest request,
                QWidget *parent = nullptr);
  QJsonObject selection;
  void discover();
signals:
  void selected(QJsonObject value);

private:
  void perform(QString action);
  bool english, writable;
  BackupRequest request;
  QLineEdit *uri, *user, *password, *domain;
  QCheckBox *remember;
  QListWidget *places;
  QLabel *status;
};

class BackupWizard : public QWizard {
  Q_OBJECT
public:
  BackupWizard(bool english, BackupRequest request, QWidget *parent = nullptr);
  QString planId;

protected:
  bool validateCurrentPage() override;
  void accept() override;
  void reject() override;

private:
  QString tx(const char *de, const char *en) const;
  void work(QJsonObject args, std::function<void(QJsonValue)> done);
  void summary();
  void exportKey();
  QJsonObject groups() const;
  bool english, working = false, completed = false;
  BackupRequest request;
  QMap<QString, QListWidget *> sourceLists;
  QMap<QString, QGroupBox *> sourceGroups;
  QJsonArray remoteSources;
  QJsonObject destination;
  QComboBox *targetKind, *serverChoice, *schedule;
  QLineEdit *target, *key, *name;
  NetworkPicker *network;
  QLabel *state, *review, *keyHint;
  QCheckBox *keySaved;
  QPushButton *exportButton;
};
