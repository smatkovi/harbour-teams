# Entwurf: Meldungen und Antworten in der Meldung

Nichts davon ist gebaut — es fehlt das Konto, an dem es zu prüfen wäre. Was
hier steht, ist nachgemessen oder aus eigenem, laufendem Code abgelesen,
damit es beim nächsten Anlauf nicht neu erarbeitet werden muss.

## Sailfish: Antwortzeile in der Meldung, mit Dienst

Lipstick zeichnet eine Textzeile statt eines Knopfes, wenn die Meldung diese
Hinweise trägt. Vorlage ist `harbour-briar/kern/src/notify.rs`, wo es seit
Monaten läuft:

```
category                        x-nemo.messaging.im
desktop_entry                   harbour-teams
x-nemo-remote-action-default    <Dienst> <Pfad> <Schnittstelle> openChat <arg>
x-nemo-remote-action-reply      <Dienst> <Pfad> <Schnittstelle> Reply <arg>
x-nemo-remote-action-type-reply input
```

Zwei Fallen, beide in Briar schon bezahlt:

* Das Argument ist **kein** Klartext, sondern ein QDataStream-QVariant
  (Typ 10, UTF-16BE), base64 kodiert — `qvariant_b64()` dort ist direkt
  übernehmbar.
* Ohne `desktop_entry` sucht lipstick das Icon nach dem Prozessnamen und
  beschwert sich, dass der Dienst keinen Startereintrag hat.
* Ohne Beschriftung in der `actions`-Liste gibt es keine Antwortzeile. Genau
  so soll die Meldung bei zugesperrter Oberfläche aussehen: sie sagt, dass
  etwas kam, und lässt niemanden an der Sperre vorbeischreiben.

Der Dienst (`teamsd`, Rust) ist dafür unvermeidlich: lipstick ruft die
Antwortmethode auf einem **laufenden** D-Bus-Namen auf, und die App läuft
nicht. Je Chat eine Meldung, nicht je Nachricht — `replaces_id` merken und
beim Lesen `CloseNotification`.

## MeeGo: kein Antwortfeld, dafür die Nachrichten-App

Harmattan kann das nicht, und zwar grundsätzlich. `MNotificationManager`
(`com.meego.core.MNotificationManager` auf `/notificationmanager`) nimmt beim
`addNotification` genau **eine** Aktion, und die ist ein D-Bus-Aufruf aus vier
Wörtern: Dienst, Pfad, Schnittstelle, Methode. Argumente lassen sich darin
nicht verlässlich unterbringen — in der Brücke steht deshalb der Chat im
*Pfad*, nicht im Argument. Ein Eingabefeld gibt es in der Meldung nicht, und
`org.freedesktop.Notifications` existiert dort überhaupt nicht.

Der Harmattan-Weg ist deshalb ein anderer: **Teams wird das sechste Protokoll
in der [Brücke](https://github.com/smatkovi/nachrichtenbruecke)**. Dann landen
die Nachrichten in der System-Nachrichten-App — und die hat Meldung *und*
Antwortzeile von Haus aus, genau wie bei WhatsApp, Signal, Briar, Telegram und
Matrix. Kein neuer bleibender Prozess, was auf dem N950 der eigentliche Punkt
ist (dort war der Arbeitsspeicher die Last, nicht die Rechenzeit).

Zu bedenken:

* Die anderen fünf Protokolle hängen an *eigenen* Diensten, die vier
  HTTP-Wege beantworten — Briar kostete in der Brücke drei Zeilen, weil
  `briard` ein eigener Prozess ist. Teams braucht keinen eigenen Prozess
  (reines HTTPS, kein Kryptostapel), gehört also **in** die Brücke. Dafür
  fehlt dort noch eine Trennfuge; die zu ziehen wäre der erste Schritt.
* Schlüssel in `kennungen.rs` ist die Chat-Kennung (`19:…@thread.v2`), der
  Name nur eine Beschriftung — sonst fallen zwei gleichnamige Chats zusammen.
* Das Konto von Hand ins rtcom-Keyfile, nicht in `accounts.db`.

Die Alternative wäre ein kurzlebiger Poller per `timed`/alarmd, der aufwacht,
meldet und wieder verschwindet. Der kostet gar keinen Speicher, verliert aber
die Echtzeit und doppelt die Brücke.

## Gemeinsam: ein Kern, zwei Abnehmer

Ein Rust-Kern (`teams-kern`) mit Token-Erneuerung, `authz`, Chatliste, Senden
und Echtzeit; daraus `teamsd` für Sailfish und ein Protokollmodul in der
Brücke für MeeGo.

**Die Token gehören dem Kern, nicht der App.** Zwei Prozesse, die denselben
Refresh-Token erneuern, geraten sich in die Haare — ein Erneuerer, eine Datei
mit 0600, und die Python-Fassungen *fragen* nach dem gültigen Access-Token
statt selbst zu erneuern. Folge: die Sailfish-Secrets-Arbeit (`TeamsWallet5`)
wird gegenstandslos, denn ein Dienst außerhalb von Sailjail kommt an diese
Sammlung ohnehin nicht heran.

Der Echtzeitweg ist noch zu lesen, nicht zu raten: `purple-teams` macht beides
— den klassischen Skype-Endpunkt-Langzug auf dem Regionsrechner, den `authz`
schon nennt, und Trouter. Der Langzug zuerst: kein WebSocket. Und er muss
wirklich blockieren, sonst rennt der Frager im Kreis.
