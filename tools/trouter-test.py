#!/usr/bin/env python3
"""Beweist, dass eine Nachricht ueber Trouter wirklich ankommt.

Legt dafuer einen eigenen Faden an, in dem niemand sonst sitzt, schickt
nach dem Anmelden eine Zeile hinein und wartet, ob sie als Ereignis
zurueckkommt.

    tools/trouter-test.py ZUSTAND [sekunden] [--faden FADEN]

Ohne --faden wird ein neuer Faden angelegt. Er bleibt stehen (loeschen
laesst sich ein Gespraech nur im offiziellen Client) -- seine Kennung
steht am Ende, damit man ihn beim naechsten Mal wiederverwenden kann.
"""

import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from teams_api import TeamsAuth
from trouter import Trouter, nachricht_aus

CT = ssl.create_default_context()


def chatsvc(auth, pfad, methode="GET", koerper=None):
    url = auth.chatsvc_base + pfad
    a = urllib.request.Request(url, data=koerper, method=methode)
    a.add_header("Authentication", "skypetoken=" + auth.skype_token)
    a.add_header("Content-Type", "application/json")
    a.add_header("Accept", "application/json; ver=1.0")
    try:
        with urllib.request.urlopen(a, context=CT, timeout=30) as r:
            return r.status, r.read().decode(errors="replace"), dict(
                (k.lower(), v) for k, v in r.headers.items())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), dict(
            (k.lower(), v) for k, v in (e.headers or {}).items())


def faden_anlegen(auth):
    """Ein Faden mit genau einem Mitglied: mir. Sieht niemand sonst."""
    koerper = json.dumps({
        "members": [{"id": f"8:{auth.skype_id}", "role": "Admin"}],
        "properties": {"threadType": "chat", "chatFilesIndexId": "2",
                       "topic": "Trouter-Probe"},
    }).encode()
    status, _, kopf = chatsvc(auth, "/v1/threads", "POST", koerper)
    ort = kopf.get("location", "")
    kennung = urllib.parse.unquote(ort.rstrip("/").rsplit("/", 1)[-1]) if ort else ""
    return status, kennung


def zeile_senden(auth, faden, text):
    enc = urllib.parse.quote(faden, safe="")
    koerper = json.dumps({
        "content": text,
        "messagetype": "Text",
        "contenttype": "text",
        "clientmessageid": str(uuid.uuid4().int % 10**18),
    }).encode()
    status, rumpf, _ = chatsvc(
        auth, f"/v1/users/ME/conversations/{enc}/messages", "POST", koerper)
    return status, rumpf[:140]


def main():
    z = json.load(open(sys.argv[1]))
    dauer = 70
    faden = None
    rest = sys.argv[2:]
    if rest and rest[0].isdigit():
        dauer = int(rest[0]); rest = rest[1:]
    if len(rest) >= 2 and rest[0] == "--faden":
        faden = rest[1]

    auth = TeamsAuth("privat")
    auth.refresh_token = z["refresh_token"]
    if not (auth.refresh_access_token() and auth.get_teams_authorization()):
        print("Anmeldung ging nicht")
        return 1
    z["refresh_token"] = auth.refresh_token
    json.dump(z, open(sys.argv[1], "w"))
    print("angemeldet als", auth.skype_id, "| id_token:",
          "ja" if auth.id_token else "NEIN (Trouter-Anmeldung ohne Bearer)")

    if not faden:
        status, faden = faden_anlegen(auth)
        print(f"Faden angelegt: HTTP {status}  {faden}")
        if not faden:
            print("ohne Faden kein Test")
            return 1
    else:
        print("Faden (vorgegeben):", faden)

    tr = Trouter(auth)
    if not tr.verbinden():
        return 1

    probe = "Trouter-Probe " + time.strftime("%H:%M:%S")
    gesehen = {"ja": False}

    def spaeter():
        # Erst wenn die Begruessung durch ist, sonst faellt die Nachricht
        # in die Luecke vor der Registrierung.
        for _ in range(40):
            if tr.angemeldet:
                break
            time.sleep(0.5)
        time.sleep(2)
        status, rumpf = zeile_senden(auth, faden, probe)
        print(f"\n>>> Zeile gesendet: HTTP {status} {rumpf[:80]}\n")

    threading.Thread(target=spaeter, daemon=True).start()

    ende = time.time() + dauer
    for ereignis in tr.lies(bis=ende):
        art = ereignis.get("resourceType", "?")
        # Ohne eigene Kennung, damit der Test die eigene Probe auch sieht --
        # im Dienst wird sie uebergeben und eigene Nachrichten fallen weg.
        n = nachricht_aus(ereignis)
        if n:
            f, absender, name, text = n
            treffer = probe in text
            print(f"EREIGNIS {art}: faden …{f[-26:]} von {absender!r} "
                  f"name {name!r} laenge {len(text)}"
                  f"{'   <== unsere Probe' if treffer else ''}")
            if treffer:
                gesehen["ja"] = True
                break
        else:
            print(f"EREIGNIS {art}")

    print()
    if gesehen["ja"]:
        print("TROUTER LIEFERT. Die Nachricht kam ueber den Kanal an.")
    else:
        print("Die Probe kam nicht an -- Kanal stand, Ereignis fehlte.")
    print("Faden fuer den naechsten Lauf:", faden)
    return 0 if gesehen["ja"] else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main())
