#!/usr/bin/env python3
"""Messt den Trouter-Weg: woher erfaehrt die App sofort von einer Nachricht?

Der klassische Langzug ist tot (POST .../v1/users/ME/endpoints gibt auf
beiden Rechnern 410 Gone). Bleibt Trouter, der Weg des Webclients. Vier
Stufen, alle hier nachgemessen:

  1  POST  go.trouter.skype.com/v4/a?epid=...   mit x-skypetoken
           ->  socketio, surl, connectparams, ccid, registrarUrl
  2  GET   {socketio}socket.io/1/?v=v4&<connectparams>&...
           ->  socket.io-v1-Handschlag: Sitzung, Herzschlag, Transporte
  3  POST  {registrarUrl}  -- erst damit wird die surl zum Postfach
  4  GET   {socketio}socket.io/1/xhr-polling/{sitzung}?...
           ->  Rahmen; in "3:::{...}" steckt ein unechtes POST mit der
               Nachricht darin

Stufe 4 geht mit xhr-polling, also ohne WebSocket -- der Handschlag bietet
beides an, und ohne WebSocket bleibt der Dienst abhaengigkeitsfrei.

    tools/trouter-probe.py ZUSTAND [sekunden] [--probe-in FADEN]

--probe-in schickt nach 15 s eine Testzeile in den genannten Faden, damit
man sieht, ob ein Ereignis ankommt. Nur in einen Faden nehmen, in dem
niemand sonst sitzt.

Pfade, Kennungen und Vorlagenschluessel aus purple-teams (EionRobb);
gemessen wird selbst.
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

CT = ssl.create_default_context()

TROUTER_PRIVAT = "https://go.trouter.skype.com/"
TCCV = "2024.23.01.2"
CLIENTINFO = "27/1.0.0.2023052414"
TTL = 86400


def ruf(url, marke, methode="GET", koerper=None, zeit=45, kopf=None):
    a = urllib.request.Request(url, data=koerper, method=methode)
    a.add_header("X-Skypetoken", marke)
    a.add_header("Accept", "application/json")
    for k, v in (kopf or {}).items():
        a.add_header(k, v)
    if koerper is not None:
        a.add_header("Content-Length", str(len(koerper)))
    try:
        with urllib.request.urlopen(a, context=CT, timeout=zeit) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return -1, str(e)


def anmelden(registrar, marke, epid, surl, app, vorlage, kontext):
    """Eine Registrierung beim Registrar -- erst damit wird die surl zum
    Postfach, in das der Dienst Ereignisse legt."""
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
    # Nur der TFL-Arbeiter darf die Endpunktkennung selbst tragen; alles
    # andere bekommt eine eigene, sonst ueberschreiben sich die Eintraege.
    kennung = epid if (app == "TeamsCDLWebWorker" and kontext == "TFL") else str(uuid.uuid4())
    koerper = json.dumps({
        "clientDescription": beschreibung,
        "registrationId": kennung,
        "nodeId": "",
        "transports": {"TROUTER": [{"context": "", "path": surl, "ttl": TTL}]},
    }).encode()
    return ruf(registrar, marke, "POST", koerper,
               kopf={"Content-Type": "application/json"})


def testzeile(auth, faden, text):
    """Schickt eine Zeile in einen Faden -- nur zum Messen."""
    enc = urllib.parse.quote(faden, safe="")
    url = f"{auth.chatsvc_base}/v1/users/ME/conversations/{enc}/messages"
    koerper = json.dumps({
        "content": text,
        "messagetype": "Text",
        "contenttype": "text",
        "clientmessageid": str(uuid.uuid4().int % 10**18),
    }).encode()
    a = urllib.request.Request(url, data=koerper, method="POST")
    a.add_header("Authentication", "skypetoken=" + auth.skype_token)
    a.add_header("Content-Type", "application/json")
    a.add_header("Accept", "application/json; ver=1.0")
    try:
        with urllib.request.urlopen(a, context=CT, timeout=30) as r:
            return r.status, r.read().decode(errors="replace")[:120]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]


def rahmen_deuten(roh):
    """socket.io v1: <typ>:<kennung>:<pfad>:<nutzlast>."""
    for stueck in roh.split("�"):          # Mehrfachrahmen sind laengenpraefixiert
        stueck = stueck.strip()
        if not stueck or stueck.isdigit():
            continue
        teile = stueck.split(":", 3)
        if len(teile) < 4:
            yield stueck[:60], None
            continue
        typ, nutz = teile[0], teile[3]
        try:
            yield typ, json.loads(nutz)
        except ValueError:
            yield typ, {"_roh": nutz[:200]}


def main():
    z = json.load(open(sys.argv[1]))
    dauer = 90
    probe_in = None
    rest = sys.argv[2:]
    if rest and rest[0].isdigit():
        dauer = int(rest[0]); rest = rest[1:]
    if len(rest) >= 2 and rest[0] == "--probe-in":
        probe_in = rest[1]

    auth = TeamsAuth("privat")
    auth.refresh_token = z["refresh_token"]
    if not (auth.refresh_access_token() and auth.get_teams_authorization()):
        print("Anmeldung ging nicht")
        return 1
    z["refresh_token"] = auth.refresh_token
    json.dump(z, open(sys.argv[1], "w"))
    marke = auth.skype_token
    epid = str(uuid.uuid4())

    # ---- 1
    status, text = ruf(TROUTER_PRIVAT + "v4/a?epid=" + urllib.parse.quote(epid),
                       marke, "POST", b"")
    print(f"1) v4/a: HTTP {status}")
    if status != 200:
        print("  ", text[:200]); return 1
    obj = json.loads(text)
    socketio = obj["socketio"].rstrip("/")
    surl = obj["surl"]
    registrar = obj.get("registrarUrl") or "https://edge.skype.com/registrar/prod/v2/registrations"
    print("   socketio: ", socketio)
    print("   surl:     ", surl[:80])
    print("   registrar:", registrar)

    # ---- 2
    felder = dict(obj.get("connectparams") or {})
    felder.update({"v": "v4",
                   "tc": json.dumps({"cv": TCCV, "ua": "TeamsCDL", "hr": "", "v": TCCV}),
                   "con_num": f"{uuid.uuid4().int % 10**13}_1",
                   "epid": epid, "auth": "true", "timeout": "40"})
    if obj.get("ccid"):
        felder["ccid"] = obj["ccid"]
    frage = urllib.parse.urlencode(felder)
    status, text = ruf(f"{socketio}/socket.io/1/?{frage}", marke)
    print(f"\n2) Handschlag: HTTP {status}  {text.strip()[:70]}")
    if status != 200:
        return 1
    sitzung, herzschlag, grenze, transporte = (text.strip().split(":") + ["", "", ""])[:4]

    # ---- 3
    print("\n3) Registrierungen:")
    for app, vorlage, kontext in (
            ("TeamsCDLWebWorker", "TeamsCDLWebWorker_2.6", "TFL"),
            ("TeamsCDLWebWorker", "TeamsCDLWebWorker_2.3", ""),
            ("SkypeSpacesWeb", "SkypeSpacesWeb_2.3", None)):
        pfad = surl if app == "TeamsCDLWebWorker" else surl.rstrip("/") + "/" + app
        s, t = anmelden(registrar, marke, epid, pfad, app, vorlage, kontext)
        print(f"   {app:18} {vorlage:22} ctx={kontext!r:6} HTTP {s} {t[:60]}")

    # ---- 4
    if probe_in:
        def spaeter():
            time.sleep(15)
            s, t = testzeile(auth, probe_in, "Probe vom Trouter-Test")
            print(f"\n   >>> Testzeile gesendet: HTTP {s} {t[:80]}\n")
        threading.Thread(target=spaeter, daemon=True).start()

    print(f"\n4) xhr-polling, {dauer} s (Herzschlag {herzschlag} s):")
    ende = time.time() + dauer
    runde = 0
    while time.time() < ende:
        runde += 1
        t0 = time.time()
        status, roh = ruf(f"{socketio}/socket.io/1/xhr-polling/{sitzung}?{frage}",
                          marke, zeit=min(60, max(10, int(ende - time.time()) + 15)))
        wartete = time.time() - t0
        if status != 200:
            print(f"   Runde {runde}: HTTP {status} nach {wartete:.1f} s -- {roh[:150]}")
            break
        gesehen = list(rahmen_deuten(roh))
        if not gesehen:
            print(f"   Runde {runde}: leer nach {wartete:5.1f} s (Herzschlag)")
            continue
        for typ, nutz in gesehen:
            if isinstance(nutz, dict) and "url" in nutz:
                koerper = nutz.get("body") or ""
                try:
                    innen = json.loads(koerper) if isinstance(koerper, str) else koerper
                except ValueError:
                    innen = {"_roh": str(koerper)[:120]}
                art = (innen or {}).get("resourceType") or (innen or {}).get("eventType") or "?"
                print(f"   Runde {runde} ({wartete:5.1f} s) Typ {typ}: {nutz['url'][:48]}  -> {art}")
                mitteilung = ((innen or {}).get("resource") or {})
                if mitteilung.get("messagetype"):
                    print(f"      Nachricht: typ={mitteilung.get('messagetype')} "
                          f"faden={str(mitteilung.get('conversationLink',''))[-30:]} "
                          f"laenge={len(str(mitteilung.get('content','')))}")
            else:
                print(f"   Runde {runde} ({wartete:5.1f} s) Typ {typ}: {str(nutz)[:70]}")
    print("\nFertig.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main())
