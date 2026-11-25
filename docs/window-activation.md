# Vorhandene Lumen-Fenster aktivieren

Ein normaler erneuter Start bringt das vorhandene App-Fenster nach vorn, hebt
Minimierung auf und erhält Reiter, maximierte Darstellung und offene Eingaben.
Ein modaler Dialog bleibt der aktive Ansprechpartner. Unter KDE erfolgt die
Aktivierung über einen KWin-Weg; PID und Lumen-App-ID
begrenzen das Ziel. Liegt das Fenster auf einem anderen virtuellen Desktop,
wechselt KWin dorthin. Andere Desktops verwenden die normale Qt-Aktivierung.

`files/lumen_activation.py` bündelt diesen Weg für Desktop, Suche, System/Sound,
lokale Tool-Fenster und Server-App-Hosts sowie Files, Updater und Companion.
Eine Aktivierung bestätigt nichts.

Files, Updater und Companion reservieren vor der Fensterkonstruktion einen
D-Bus-Dienst. Weitere Starts erreichen das bestehende Fenster, auch während
dessen Aufbau. Tool-Fenster verwenden weiterhin ihre privaten Socket-Endpunkte
und Bibliothekssperren; die Sperre wird jetzt vor der Fensterkonstruktion erworben.
Ein zweiter Start wartet begrenzt auf den ersten, statt zweite Hintergrundjobs
und ein unnötiges Zwischenfenster anzulegen.

Eine ausdrücklich übergebene Datei oder ein Ordner öffnet sich bei Files in
einem zusätzlichen Reiter; `--select` unterstützt auch lokale Datei-URIs.
Explizite Auftrags-, Bereichs- und Übergabelinks behalten ihre Navigation.
Bewusst neue Gesprächskontexte und einzelne Freigabe-/Aufnahmedialoge behalten
ihre eigenständigen Fenster. Das KDE-Benachrichtigungszentrum bleibt ein Panel.
