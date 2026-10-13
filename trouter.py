#!/usr/bin/env python3
"""Trouter: der Weg, auf dem Teams von sich aus Bescheid gibt.

Warum nicht der Langzug: die Endpunkt-Anmeldung dafuer
(`POST /v1/users/ME/endpoints`) ist abgeschaltet, 410 Gone auf beiden
Rechnern. Trouter ist, was der Webclient benutzt.

Warum ohne WebSocket: der socket.io-Handschlag bietet neben `websocket`
auch `xhr-polling` an. Damit ist Empfangen ein `GET` und Senden ein `POST`
auf dieselbe Adresse -- kein Fremdpaket, nichts zu kompilieren, und auf
einem Telefon ein Prozess weniger, der etwas mitbringen muss.

Der Ablauf, gemessen am 13.10.2026 (siehe BEFUND-privatkonto.md):

  1  POST  go.trouter.skype.com/v4/a?epid=<uuid>   Kopf X-Skypetoken
           ->  socketio, surl, connectparams, ccid, registrarUrl
  2  GET   {socketio}/socket.io/1/?v=v4&<connectparams>&...
           ->  "<sitzung>:<herzschlag>:<grenze>:websocket,xhr-polling"
  3  Rahmen `1::` abwarten, dann user.authenticate, user.activity und die
     Registrierungen beim Registrar (dessen Adresse der Dienst nennt -- V3,
     nicht die V2 aus purple-teams).
  4  Empfangen. **Jeder `3:::`-Rahmen ist eine Anfrage und will eine
     Quittung.** Ohne sie laeuft es im Kreis: endlos `trouter.connected`,
     dann `trouter.message_loss` (44 Runden in 75 s nachgemessen).

Die Rahmenform ist socket.io v1: `<typ>:<kennung>:<pfad>:<daten>`, mehrere
Rahmen in einer Antwort getrennt durch U+FFFD<laenge>U+FFFD.
"""

import base64
import gzip
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

TROUTER = {
    "privat": "https://go.trouter.skype.com/",
    "arbeit": "https://go.trouter.teams.microsoft.com/",
}
# Nur als Rueckfall: der Dienst nennt die Adresse selbst in registrarUrl.
REGISTRAR = {
    "privat": "https://edge.skype.com/registrar/prod/V3/registrations",
    "arbeit": "https://teams.microsoft.com/registrar/prod/V2/registrations",
}
TCCV = "2024.23.01.2"
CLIENTINFO = "27/1.0.0.2023052414"
TTL = 86400
TRENNER = "�"

# Welche Arbeiter angemeldet werden. Der TFL-Arbeiter muss zuletzt kommen
# und darf als einziger die Endpunktkennung tragen -- sonst ueberschreiben
# sich die Eintraege gegenseitig.
ARBEITER_PRIVAT = [
    ("SkypeSpacesWeb", "SkypeSpacesWeb_2.3", None),
    ("TeamsCDLWebWorker", "TeamsCDLWebWorker_2.3", ""),
    ("TeamsCDLWebWorker", "TeamsCDLWebWorker_2.6", "TFL"),
]
ARBEITER_ARBEIT = [
    ("SkypeSpacesWeb", "SkypeSpacesWeb_2.3", None),
    ("TeamsCDLWebWorker", "TeamsCDLWebWorker_2.1", None),
]


def _entpacken(text, gezippt):
    """base64 und gzip, wie der Dienst sie schachtelt."""
    rohdaten = base64.b64decode(text)
    if gezippt:
        try:
            return gzip.decompress(rohdaten).decode("utf-8", "replace")
        except OSError:
            pass
    return rohdaten.decode("utf-8", "replace")


class Trouter:
    """Eine Trouter-Sitzung. `lies()` liefert Ereignisse, bis sie abreisst."""

    def __init__(self, auth, melder=print, epid=None):
        self.auth = auth
        self.melde = melder
        # Die Endpunktkennung muss **bleiben**. Mit einer neuen je Sitzung
        # entsteht beim Registrar jedes Mal ein weiterer Eintrag, und der
        # Dienst liefert dann an einen alten, toten Pfad -- nachgemessen:
        # nach einem Neustart kam kein Ereignis mehr an. purple-teams haelt
        # sie darum je Konto fest, nicht je Verbindung.
        self.epid = epid or str(uuid.uuid4())
        self.zusammenhang = ssl.create_default_context()
        self.socketio = None
        self.surl = None
        self.registrar = None
        self.sitzung = None
        self.frage = None
        self.connectparams = {}
        self.herzschlag = 70
        self.angemeldet = False
        # Dasselbe Ereignis kommt mehrfach: zwei TeamsCDLWebWorker-
        # Registrierungen zeigen auf dieselbe surl, und was nicht sofort
        # quittiert ist, schickt der Dienst noch einmal. Acht Meldungen fuer
        # eine Nachricht nachgemessen. Also merken, was schon durch war.
        self._gesehen = []
        self._gesehen_satz = set()

    # ------------------------------------------------------------ Netz

    def _ruf(self, url, methode="GET", koerper=None, zeit=60, kopf=None):
        anfrage = urllib.request.Request(url, data=koerper, method=methode)
        anfrage.add_header("X-Skypetoken", self.auth.skype_token)
        for k, v in (kopf or {}).items():
            anfrage.add_header(k, v)
        if koerper is not None:
            anfrage.add_header("Content-Length", str(len(koerper)))
        try:
            with urllib.request.urlopen(anfrage, context=self.zusammenhang, timeout=zeit) as a:
                return a.status, a.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:                      # Zeitgrenze, Leitung weg
            return -1, str(e)

    # -------------------------------------------------------- Aufbauen

    def verbinden(self):
        """Stufen 1 und 2. Gibt True zurueck, wenn die Sitzung steht."""
        modus = getattr(self.auth, "modus", "privat")
        basis = TROUTER.get(modus, TROUTER["privat"])
        status, text = self._ruf(basis + "v4/a?epid=" + urllib.parse.quote(self.epid),
                                 "POST", b"", zeit=45)
        if status != 200:
            self.melde(f"trouter: v4/a gab {status}: {text[:160]}")
            return False
        obj = json.loads(text)
        self.socketio = obj["socketio"].rstrip("/")
        self.surl = obj["surl"]
        self.registrar = obj.get("registrarUrl") or REGISTRAR.get(modus)
        self.connectparams = dict(obj.get("connectparams") or {})

        felder = dict(self.connectparams)
        felder.update({
            "v": "v4",
            "tc": json.dumps({"cv": TCCV, "ua": "TeamsCDL", "hr": "", "v": TCCV}),
            "con_num": f"{uuid.uuid4().int % 10**13}_1",
            "epid": self.epid,
            "auth": "true",
            "timeout": "40",
        })
        if obj.get("ccid"):
            felder["ccid"] = obj["ccid"]
        self.frage = urllib.parse.urlencode(felder)

        status, text = self._ruf(f"{self.socketio}/socket.io/1/?{self.frage}", zeit=45)
        if status != 200:
            self.melde(f"trouter: Handschlag gab {status}: {text[:160]}")
            return False
        teile = (text.strip().split(":") + ["", "", ""])[:4]
        self.sitzung = teile[0]
        try:
            self.herzschlag = int(teile[1])
        except ValueError:
            self.herzschlag = 70
        self.melde(f"trouter: Sitzung {self.sitzung[:12]}…, Herzschlag {self.herzschlag} s, "
                   f"Transporte {teile[3]}")
        return True

    @property
    def _kanal(self):
        return f"{self.socketio}/socket.io/1/xhr-polling/{self.sitzung}?{self.frage}"

    def _senden(self, rahmen):
        status, text = self._ruf(self._kanal, "POST", rahmen.encode("utf-8"), zeit=30,
                                 kopf={"Content-Type": "text/plain;charset=UTF-8"})
        if status not in (200, 204):
            self.melde(f"trouter: Senden gab {status}: {text[:120]}")
        return status in (200, 204)

    # ------------------------------------------------------- Anmelden

    def _anmelderahmen(self):
        kopf = {"X-Ms-Test-User": "False", "X-MS-Migration": "True"}
        if getattr(self.auth, "id_token", None):
            kopf["Authorization"] = "Bearer " + self.auth.id_token
        return "3:::" + json.dumps({
            "name": "user.authenticate",
            "args": [{"headers": kopf, "connectparams": self.connectparams}],
        })

    def _registrieren(self):
        modus = getattr(self.auth, "modus", "privat")
        arbeiter = ARBEITER_PRIVAT if modus == "privat" else ARBEITER_ARBEIT
        for app, vorlage, kontext in arbeiter:
            beschreibung = {
                "appId": app,
                "aesKey": "",
                "languageId": "en-US",
                "platform": "edge",
                "templateKey": vorlage,
                "platformUIVersion": CLIENTINFO,
            }
            if kontext is not None:
                beschreibung["productContext"] = kontext
            eigen = app == "TeamsCDLWebWorker" and (kontext == "TFL" or modus != "privat")
            pfad = self.surl if app == "TeamsCDLWebWorker" else self.surl.rstrip("/") + "/" + app
            koerper = json.dumps({
                "clientDescription": beschreibung,
                "registrationId": self.epid if eigen else str(uuid.uuid4()),
                "nodeId": "",
                "transports": {"TROUTER": [{"context": "", "path": pfad, "ttl": TTL}]},
            }).encode()
            status, text = self._ruf(self.registrar, "POST", koerper, zeit=45,
                                     kopf={"Content-Type": "application/json"})
            if status not in (200, 202):
                self.melde(f"trouter: Registrierung {app}/{vorlage} gab {status}: {text[:120]}")

    def _begruessen(self):
        """Was nach dem `1::` zu tun ist, in dieser Reihenfolge."""
        self._senden(self._anmelderahmen())
        self._senden("3:::" + json.dumps({
            "name": "user.activity",
            "args": [{"state": "active", "cv": uuid.uuid4().hex[:21] + "Q.0.1"}],
        }))
        self._registrieren()
        self.angemeldet = True
        self.melde("trouter: angemeldet und registriert")

    # ------------------------------------------------------- Empfangen

    def _rahmen(self, roh):
        """Die Rahmen einer Antwort, in der Reihenfolge, in der sie kamen."""
        if roh.startswith(TRENNER):
            stuecke, rest = [], roh
            while rest.startswith(TRENNER):
                rest = rest[1:]
                laenge, _, rest = rest.partition(TRENNER)
                try:
                    n = int(laenge)
                except ValueError:
                    break
                stuecke.append(rest[:n])
                rest = rest[n:]
            return stuecke
        return [roh] if roh else []

    def _ereignis(self, nutzlast):
        """Aus einem `3:::`-Anfragerahmen die eigentliche Nachricht schaelen."""
        kopf = nutzlast.get("headers") or {}
        rumpf = nutzlast.get("body") or ""
        if kopf.get("X-Microsoft-Skype-Content-Encoding") == "gzip":
            rumpf = _entpacken(rumpf, True)
        try:
            innen = json.loads(rumpf) if isinstance(rumpf, str) else rumpf
        except ValueError:
            return None
        if not isinstance(innen, dict):
            return None
        # Die Nutzlast steckt manchmal noch einmal verpackt darin.
        if "cp" in innen:
            try:
                innen = json.loads(_entpacken(innen["cp"], True))
            except Exception:
                return None
        elif "gp" in innen:
            try:
                innen = json.loads(_entpacken(innen["gp"], False))
            except Exception:
                return None
        return innen

    def _schon_gehabt(self, ereignis):
        """True, wenn dieses Ereignis bereits durchgereicht wurde.

        Geschluessel wird nach der Nachrichtenkennung; fehlt die, nach
        Gespraech und Zeitstempel. Die letzten 400 reichen -- mehr
        Wiederholungen kommen nicht, und der Speicher ist knapp.
        """
        r = ereignis.get("resource") or {}
        schluessel = (str(ereignis.get("resourceType", "")) + "|"
                      + str(r.get("id") or r.get("clientmessageid") or "") + "|"
                      + str(r.get("conversationLink", "")) + "|"
                      + str(r.get("originalarrivaltime") or r.get("composetime") or ""))
        if schluessel in self._gesehen_satz:
            return True
        self._gesehen.append(schluessel)
        self._gesehen_satz.add(schluessel)
        if len(self._gesehen) > 400:
            self._gesehen_satz.discard(self._gesehen.pop(0))
        return False

    def lies(self, bis=None):
        """Liest, bis die Sitzung abreisst (oder `bis` erreicht ist).

        Gibt jedes Ereignis als dict weiter -- die Form, die chatsvc auch
        sonst benutzt: resourceType, resource, …
        """
        while bis is None or time.time() < bis:
            zeit = 60 if bis is None else max(10, min(60, int(bis - time.time()) + 15))
            status, roh = self._ruf(self._kanal, zeit=zeit)
            if status != 200:
                self.melde(f"trouter: Kanal gab {status} -- Sitzung zu Ende")
                return
            for stueck in self._rahmen(roh):
                if not stueck:
                    continue
                typ = stueck.split(":", 1)[0]
                if typ == "1":
                    if not self.angemeldet:
                        self._begruessen()
                    continue
                if typ == "2":
                    self._senden("2::")          # Herzschlag zurueck
                    continue
                teile = stueck.split(":", 3)
                if len(teile) < 4:
                    continue
                try:
                    nutzlast = json.loads(teile[3]) if teile[3] else {}
                except ValueError:
                    continue
                if typ == "3" and isinstance(nutzlast, dict) and "id" in nutzlast:
                    # Erst quittieren, dann auswerten: ohne Quittung schickt
                    # der Dienst dasselbe wieder und wieder.
                    self._senden("3:::" + json.dumps(
                        {"id": nutzlast["id"], "status": 200, "body": ""}))
                    ereignis = self._ereignis(nutzlast)
                    if ereignis and not self._schon_gehabt(ereignis):
                        yield ereignis
                elif typ == "5" and isinstance(nutzlast, dict):
                    name = nutzlast.get("name", "")
                    if name not in ("trouter.connected", "trouter.message_loss"):
                        self.melde(f"trouter: {name}")


def _kennung_aus(verweis):
    """Aus einem Ressourcenverweis die nackte Kennung.

    `from` und `conversationLink` kommen als volle Adressen, etwa
    https://notifications.skype.net/v1/users/ME/contacts/8:grinsgesicht --
    gebraucht wird nur das letzte Stueck.
    """
    if not verweis:
        return ""
    return urllib.parse.unquote(str(verweis).rstrip("/").rsplit("/", 1)[-1])


def nachricht_aus(ereignis, eigene_kennung=None):
    """Macht aus einem Trouter-Ereignis das, was eine Meldung braucht.

    Rueckgabe: (faden, absenderkennung, anzeigename, text) oder None, wenn
    es keine neue fremde Nachricht ist.

    Eigene Nachrichten kommen auch an -- der Dienst schickt sie an alle
    Endpunkte des Kontos, damit andere Geraete mitkommen. Fuer eine Meldung
    sind sie genau falsch, deshalb raus damit.
    """
    if (ereignis.get("resourceType") or "") != "NewMessage":
        return None
    r = ereignis.get("resource") or {}
    if r.get("messagetype") not in ("Text", "RichText/Html"):
        return None
    absender = _kennung_aus(r.get("from"))
    if eigene_kennung and absender == eigene_kennung:
        return None
    return (_kennung_aus(r.get("conversationLink")),
            absender,
            r.get("imdisplayname") or "",
            r.get("content") or "")


if __name__ == "__main__":
    print(__doc__)
    sys.exit(0)
