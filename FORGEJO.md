# Lumen Desktop auf Forgejo

Die maßgebliche private Quellveröffentlichung liegt unter
[ativaro/lumen](https://forge.example.invalid/ativaro/lumen). Neue Desktop-Installationen
verwenden den dortigen `main`-Stand und den authentifizierten Installationsweg
in [INSTALL.md](INSTALL.md). Ein Browserlogin allein authentifiziert Git nicht.
Zugangsdaten niemals in Clone-URLs, Skriptargumente oder Dokumentation schreiben.

Der aktuelle Updater verwendet für frühere offizielle GitHub-Installationen
und für Installationen ohne gespeicherte Quelle Forgejo. Wer noch den alten
Updater hat, kann ihn einmal aus dem Forgejo-Checkout starten. Eine ausdrücklich
konfigurierte eigene Repository-Adresse gilt weiter. Der Updater prüft vor der
Installation, ob der Kandidat die bereits verwendeten Server-Apps und die native
Topbar mitbringt. Dieser Desktop-Stand wird auf dem privaten Forgejo veröffentlicht.

Das Repository enthält verteilbare Quellen, Tests, Anleitungen und Assets.
Private Konfiguration, Modelle, Nutzerdaten, Serverzugänge und Sicherungen
gehören nicht hinein. Ein Quellpush ist weder eine Installation auf dem
Desktop noch ein Serverdeployment oder eine neue Mobile-Ausgabe.

[Veröffentlichung und Prüfungen](PUBLISHING.md) ·
[historische Quellbelege](PUBLICATION.md)
