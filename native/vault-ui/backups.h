// SPDX-License-Identifier: MIT
#pragma once
#include <QtNetwork>
#include <QtWidgets>
#include <functional>
class BackupPage : public QWidget {
  Q_OBJECT
public:
  explicit BackupPage(QWidget *tabs, bool english, QWidget *parent = nullptr);
  void activate();
  bool editing() const { return dialogOpen; }

private:
  using Done = std::function<void(QJsonValue)>;
  QString tx(const char *de, const char *en) const;
  QPushButton *button(const QString &text, std::function<void()> action);
  void rpc(QJsonObject request, std::function<void(QJsonObject)> done,
           int retries = 20);
  void start(QJsonObject request, Done done = {},
             std::function<void(QString)> failed = {});
  void poll();
  void state(QJsonObject value);
  void reload(QString selected = {});
  void select();
  void create();
  void run(QString op, QJsonObject extra = {});
  void restore(QString snapshot, QString selected = {});
  void lumenSources();
  void error(const QString &message);
  QString snapshot();
  bool english, busy = false, polling = false, dialogOpen = false;
  bool archived = false, loaded = false;
  QString socketPath, identity, token, lastOutcome;
  Done completion;
  std::function<void(QString)> failure;
  QMap<QString, QLabel *> coverage;
  QPushButton *resumeSetup;
  QJsonArray plans;
  QListWidget *listing, *sources;
  QTreeWidget *snapshots;
  QLineEdit *search;
  QLabel *title, *details, *status;
  QWidget *controls;
  QStackedWidget *pages;
  QComboBox *interval;
  QPushButton *cancel;
  QTimer timer;
};
