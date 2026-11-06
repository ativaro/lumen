# Lumen Desktop: Quellen und Updates

Ab Version 1.2.0-116 liegt der offizielle Desktop-Updatekanal auf
[GitHub · ativaro/lumen](https://github.com/ativaro/lumen), Branch `main`.
Das Repository bleibt privat. Der vorhandene private
[Forgejo-Stand](https://forge.example.invalid/ativaro/lumen) wird mit demselben Quellinhalt
weitergeführt. Zugangsdaten gehören niemals in Clone-URLs oder Skriptargumente.

Der aktuelle Updater verwendet GitHub auch für bisherige offizielle
Forgejo-Installationen und Installationen ohne gespeicherte Quelle.
Eine ausdrücklich konfigurierte eigene Repository-Adresse gilt weiter.
Der Updater prüft vor der Installation, ob der Kandidat die bereits verwendeten
Server-Apps und die native Topbar mitbringt. Alte Updatepläne werden beim
Quellenwechsel abgewiesen; Quellcaches bleiben nach Repository getrennt.

Das Repository enthält verteilbare Quellen, Tests, Anleitungen und Assets.
Private Konfiguration, Modelle, Nutzerdaten, Serverzugänge und Sicherungen
gehören nicht hinein. Ein Quellpush ist keine Desktop-Installation und kein
Serverdeployment oder Mobile-Release.

[Installation](INSTALL.md) · [Veröffentlichung und Prüfungen](PUBLISHING.md) ·
[historische Quellbelege](PUBLICATION.md)
