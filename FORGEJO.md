# Lumen Desktop: Quellen und Updates

Lumen Desktop wird über zwei getrennte Quellen verteilt:

- **Intern / internal-desktop:** [Forgejo · ativaro/lumen](https://forge.example.invalid/ativaro/lumen), Branch `main`.
- **Tester:** [GitHub · ativaro/lumen](https://github.com/ativaro/lumen), Branch `main`.

Beide Repositories bleiben privat und enthalten denselben geprüften Quellinhalt.
Tester benötigen Zugriff auf GitHub, aber keinen Zugang zum internen Forgejo.
Zugangsdaten gehören niemals in Clone-URLs oder Skriptargumente.

Ab Version 1.2.0-117 verwendet der Updater die bei der Installation gespeicherte
Quelle. Forgejo bleibt Forgejo; GitHub bleibt GitHub. Eigene Repository-Adressen
bleiben ebenfalls erhalten. Nur wenn keine Quelle gespeichert ist, gilt GitHub
als Standard. Es erfolgt keine automatische Umleitung zwischen den Kanälen.
Der Updater prüft vor der Installation, ob der Kandidat die bereits verwendeten
Server-Apps und die native Topbar mitbringt. Alte Updatepläne werden beim
Quellenwechsel abgewiesen; Quellcaches bleiben nach Repository getrennt.

Das Repository enthält verteilbare Quellen, Tests, Anleitungen und Assets.
Private Konfiguration, Modelle, Nutzerdaten, Serverzugänge und Sicherungen
gehören nicht hinein. Ein Quellpush ist keine Desktop-Installation und kein
Serverdeployment oder Mobile-Release.

[Installation](INSTALL.md) · [Veröffentlichung und Prüfungen](PUBLISHING.md) ·
[historische Quellbelege](PUBLICATION.md)
