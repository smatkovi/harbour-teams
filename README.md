# Teams für Sailfish OS und MeeGo Harmattan

Ein eigener, nativer Microsoft-Teams-Client — kein Port und kein Mantel um
die Webseite. Zweimal dieselbe Idee: `teams_api.py` spricht die Teams-Dienste
direkt, darüber liegt je eine Oberfläche in QML.

| | Sailfish OS | MeeGo Harmattan |
|---|---|---|
| Fassung | 0.1.0-73 | 0.9.22 |
| Oberfläche | Silica, sechs Seiten | `com.nokia.meego`, ein `main.qml` |
| Gerüst | `sailfish-qml` + PyOtherSide (`teams_bridge.py`) | Python 2.7 mit PySide, `QDeclarativeView` |
| Python | das des Systems | 2.7 zeichnet, `/opt/wunderw/bin/python3.11` arbeitet |
| Token | Sailfish Secrets (`TeamsWallet5`) | `~/.config/teams/tokens.json` |
| Verzeichnis | `/usr/share/harbour-teams` | `/opt/teams` |

## Wie die Anmeldung geht

Device-Code-Flow gegen `login.microsoftonline.com/common` mit der Kennung
`04b07795-8ddb-461a-bbee-02f9e1bf7b46` — das ist die Azure-CLI-Kennung, deren
Bereiche vorab zugestimmt sind. Kein eigener Mandant, keine App-Registrierung,
keine Attestierung. Der Access-Token wird bei
`teams.microsoft.com/api/authsvc/v1.0/authz` gegen einen **Skypetoken**
getauscht; dieselbe Antwort nennt den Regionsrechner
(`emea.ng.msg.teams.microsoft.com`), auf dem die Chats liegen.

Danach sprechen beide Fassungen denselben Stapel:

* `teams.microsoft.com/api/chatsvc/…` — Chats, Nachrichten, Senden, Löschen
* `teams.microsoft.com/api/mt/emea/…` — Teams und Kanäle
* `eu-prod.asyncgw.teams.microsoft.com` und `eu-api.asm.skype.com` — Dateien
  und Bilder (AMS)
* `graph.microsoft.com` — Benutzer, Gruppen, Profilbilder

Auf Harmattan ist der Umweg über das neuere Python nicht Bequemlichkeit,
sondern Pflicht: das eigene Python 2.6/2.7 bringt die TLS-Fassung nicht mehr
zusammen, die Microsoft verlangt. Der Starter hält dafür eine Warteschlange
und schickt pro Aufruf **ein** JSON-Kommando über stdin an `teams_api.py`.

## Stand: ruht

**Es gibt kein Teamskonto mehr, mit dem das hier zu prüfen wäre** (Oktober
2026). Der Weg selbst ist intakt — der Device-Code-Flow antwortet weiter mit
`200`, nachgemessen am 10.10.2026. Was abgelaufen ist, ist nur das alte Token,
und zwar an Untätigkeit:

```
AADSTS700082: The refresh token has expired due to inactivity.
The token was issued on 2025-12-18 and was inactive for 90.00:00:00
```

Mit einem Konto geht es also an derselben Stelle weiter.

## Woher dieser Quellbaum kommt

Er ist aus den gebauten Paketen rekonstruiert, nicht gewachsen. Der
ursprüngliche Baum entstand im November 2025 in einer Sandkiste
(`Build Host: runsc`) und wurde nie weggeschoben; erhalten blieben nur die
Pakete. Das ging verlustfrei, weil beide reiner Klartext sind — `noarch`
beziehungsweise `all`, keine kompilierte Zeile, keine `.pyc`:

* Sailfish aus `harbour-teams-0.1.0-73.noarch.rpm`
* MeeGo aus `teams-0.9.22_all.deb`

Neu geschrieben werden musste nur die Verpackung, die in Binärpaketen nicht
mitfährt: `rpm/harbour-teams.spec` und `meego/{control.in,build-deb.sh}`.
Dabei zwei Dinge korrigiert, die im alten Paket fehlten — die `Requires` des
RPM nennen jetzt alle fünf QML-Module, die geladen werden (fehlt eines, lädt
`harbour-teams.qml` gar nicht und die App reagiert auf das Antippen mit
nichts), und die `Depends` des Deb nennen PySide und `qt-components`, ohne die
der Starter nicht hochkommt. Die `URL` im alten RPM-Kopf zeigte auf
`github.com/nicknisi/harbour-teams` — eine Vorlagenleiche, die es nicht gibt.

Nicht übernommen wurden zwei Bauabfälle aus dem Deb: `qml/main.qml.bak` (die
Fassung vor 0.9.22, 282 Zeilen Unterschied) und `qml/main.qml.patch` (neun
Zeilen, der schwarze Balken über dem Wischbereich — in `main.qml` längst
eingebaut).

## Bauen

Sailfish, im SDK-Container:

```sh
mb2 -t SailfishOS-5.2.0.15-aarch64 build      # noarch, Ziel ist beliebig
```

MeeGo, überall wo Python 3 läuft (auch am Gerät — es wird nichts kompiliert):

```sh
meego/build-deb.sh 0.9.23
```

`mkdeb.py` schreibt das Deb selbst, weil Harmattans `dpkg` 1.15 mit dem
Schrägstrich hinter den ar-Membernamen von GNU `ar` nie getestet wurde. Das
Ergebnis ist reproduzierbar.

Eigene Debs **immer** mit `aegis-dpkg -i` installieren, sonst lässt sich aus
dem Paket nichts starten.

## Was fehlt

Beide Fassungen können nur Chat, und beide erfahren von einer neuen Nachricht
erst, wenn man die App öffnet: es gibt keinen Echtzeitweg und keine Meldung.
`Nemo.Notifications` wird in der Sailfish-Fassung importiert, aber nur für das
Fehlerbanner beim Hochladen.

Der Entwurf für Meldungen samt Antworten liegt in
[`ENTWURF-meldungen.md`](ENTWURF-meldungen.md). Videokonferenz ist kein Ziel:
die Teams-Anrufsignalisierung ist nirgends veröffentlicht oder nachgebaut, und
im Browser des Geräts geht es ohnehin.
