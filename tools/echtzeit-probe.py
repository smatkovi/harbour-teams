#!/usr/bin/env python3
"""Sucht den Echtzeitweg: woher erfaehrt man von einer neuen Nachricht?

Ohne das gibt es keine Meldung, und ohne Meldung keine Antwort darin. Zwei
Kandidaten, beide vom Teams-Webclient benutzt:

  Langzug   Endpunkt anmelden, abonnieren, dann blockierend fragen
            (POST .../subscriptions/0/poll). Kein WebSocket, haelt die
            Verbindung offen und antwortet, sobald etwas kommt.
  Trouter   ein WebSocket mit eigener Anmeldung. Mehr Teile, mehr Fallen.

Der Langzug zuerst. Gemessen wird, nicht geraten.

    tools/echtzeit-probe.py ZUSTAND [sekunden]

ZUSTAND ist die Datei von tools/anmeldeprobe.py. Inhalte werden nicht
ausgegeben -- nur Art und Anzahl der Ereignisse.
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import teams_api
from teams_api import TeamsAuth

CT = ssl.create_default_context()


def ruf(url, marke, methode="GET", koerper=None, zeit=30):
    anfrage = urllib.request.Request(url, data=koerper, method=methode)
    anfrage.add_header("Authentication", "skypetoken=" + marke)
    anfrage.add_header("Accept", "application/json; ver=1.0")
    anfrage.add_header("Content-Type", "application/json")
    anfrage.add_header("BehaviorOverride", "redirectAs404")
    try:
        with urllib.request.urlopen(anfrage, context=CT, timeout=zeit) as a:
            text = a.read().decode(errors="replace")
            kopf = {k.lower(): v for k, v in a.headers.items()}
            try:
                return a.status, json.loads(text) if text else {}, kopf
            except ValueError:
                return a.status, {"_roh": text[:400]}, kopf
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        kopf = {k.lower(): v for k, v in (e.headers or {}).items()}
        try:
            return e.code, json.loads(text) if text else {}, kopf
        except ValueError:
            return e.code, {"_roh": text[:400]}, kopf


def main():
    z = json.load(open(sys.argv[1]))
    dauer = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    auth = TeamsAuth("privat")
    auth.refresh_token = z["refresh_token"]
    if not (auth.refresh_access_token() and auth.get_teams_authorization()):
        print("Anmeldung ging nicht")
        return 1
    z["refresh_token"] = auth.refresh_token
    json.dump(z, open(sys.argv[1], "w"))
    basis, marke = auth.chatsvc_base, auth.skype_token
    print("chatsvc:", basis)

    # 1) Endpunkt anmelden. Der Webclient schickt dabei seine Faehigkeiten mit.
    koerper = json.dumps({
        "startingTimeSpan": 0,
        "endpointFeatures": "Agent,Presence2015,MessageProperties,"
                            "CustomUserProperties,NotificationStream,"
                            "SupportsSkipRosterFromThreads",
        "subscriptions": [{
            "channelType": "HttpLongPoll",
            "interestedResources": [
                "/v1/users/ME/conversations/ALL/properties",
                "/v1/users/ME/conversations/ALL/messages",
                "/v1/threads/ALL",
            ],
        }],
    }).encode()
    status, antwort, kopf = ruf(f"{basis}/v1/users/ME/endpoints", marke, "POST", koerper)
    print(f"\n1) Endpunkt anmelden: HTTP {status}")
    kennung = None
    for feld in ("set-registrationtoken", "setregistrationtoken", "registrationtoken"):
        if feld in kopf:
            print(f"   {feld}: {kopf[feld][:70]}...")
    # Die Endpunktkennung steht im location-Kopf oder in der Antwort.
    if "location" in kopf:
        print("   location:", kopf["location"][:110])
    for pfad in (("endpoint", "id"), ("id",)):
        stelle = antwort
        for teil in pfad:
            stelle = stelle.get(teil) if isinstance(stelle, dict) else None
        if isinstance(stelle, str):
            kennung = stelle
            break
    if not kennung and "subscriptions" in antwort:
        kennung = (antwort.get("subscriptions") or [{}])[0].get("id")
    print("   Antwortfelder:", sorted(antwort.keys())[:10])
    if kennung:
        print("   Endpunktkennung:", kennung[:60])
    if status >= 400:
        print("   ", json.dumps(antwort)[:400])
        return 1

    # 2) Abonnement -- der Endpunkt bringt es schon mit; der Weg dorthin
    #    steht im location-Kopf, der die volle Abonnementadresse nennt.
    abo = kopf.get("location")
    if not abo:
        print("\n2) kein location-Kopf -- ohne Abonnementadresse kein Langzug")
        return 1
    if not abo.startswith("http"):
        abo = basis.rstrip("/") + "/" + abo.lstrip("/")
    print("\n2) Abonnement:", abo[:110])

    # 3) Langzug. Er *muss* blockieren -- wer nicht wartet, laesst den
    #    Frager im Kreis rennen.
    pollurl = abo.rstrip("/") + "/poll"
    print(f"\n3) Langzug auf {pollurl[:100]}")
    ende = time.time() + dauer
    runde = 0
    while time.time() < ende:
        runde += 1
        t0 = time.time()
        status, antwort, _ = ruf(pollurl, marke, "POST", b"", zeit=min(45, int(ende - time.time()) + 10))
        gewartet = time.time() - t0
        ereignisse = antwort.get("eventMessages") or []
        arten = {}
        for e in ereignisse:
            arten[e.get("resourceType", "?")] = arten.get(e.get("resourceType", "?"), 0) + 1
        print(f"   Runde {runde}: HTTP {status} nach {gewartet:5.1f} s, "
              f"{len(ereignisse)} Ereignis(se) {arten if arten else ''}")
        if status >= 400:
            print("   ", json.dumps(antwort)[:300])
            break
        if gewartet < 1 and not ereignisse:
            print("   WARNUNG: kehrt sofort und leer zurueck -- das ist kein Langzug")
            break
    print("\nFertig.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main())
