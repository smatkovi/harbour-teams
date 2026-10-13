#!/usr/bin/env python3
"""Probe: kommt ein Konto an Teams heran -- geschaeftlich oder privat?

Nur urllib, keine Fremdpakete: so laeuft es auch dort, wo requests fehlt oder
im Sandkasten unsichtbar ist (siehe Sailjail).

    tools/anmeldeprobe.py start  arbeit|privat [ZUSTAND]
    tools/anmeldeprobe.py warten ZUSTAND
    tools/anmeldeprobe.py authz  ZUSTAND
    tools/anmeldeprobe.py chats  ZUSTAND

Zwei Wege, die nichts miteinander zu tun haben:

  arbeit  Azure-CLI-Kennung, AAD v1 mit resource=, Skypetoken von
          teams.microsoft.com/api/authsvc/v1.0/authz. Nur Arbeits- und
          Schulkonten -- /common v1 kennt keine privaten.
  privat  Die Kennung des privaten Teams-Clients, v2.0 unter /consumers,
          und als Bereich der MBI_SSL-Dienstname (kein /.default -- den
          weist Azure mit AADSTS70011 ab). Skypetoken von
          teams.live.com/api/auth/v1.0/authz/consumer, Chat unter
          teams.live.com/api/chatsvc/consumer.

Die Kennungen und Wege stammen aus purple-teams (EionRobb), nicht geraten.
"""

import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MODI = {
    "arbeit": {
        "client": "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
        "devicecode": "https://login.microsoftonline.com/common/oauth2/devicecode",
        "token": "https://login.microsoftonline.com/common/oauth2/token",
        "feld": ("resource", "https://api.spaces.skype.com"),
        "codefeld": "code",
        "authz": "https://teams.microsoft.com/api/authsvc/v1.0/authz",
        "chatsvc": None,            # steht in regionGtms
    },
    "privat": {
        "client": "8ec6bc83-69c8-4392-8f08-b3c986009232",
        "devicecode": "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
        "token": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        "feld": ("scope", "service::api.fl.spaces.skype.com::MBI_SSL openid profile offline_access"),
        "codefeld": "device_code",
        "authz": "https://teams.live.com/api/auth/v1.0/authz/consumer",
        "chatsvc": "https://teams.live.com/api/chatsvc/consumer",
    },
}


def post(url, felder, kopf=None, roh=None):
    if roh is None:
        daten = urllib.parse.urlencode(felder).encode()
        art = "application/x-www-form-urlencoded"
    else:
        daten, art = roh, "application/json"
    anfrage = urllib.request.Request(url, data=daten, method="POST")
    anfrage.add_header("Content-Type", art)
    for k, v in (kopf or {}).items():
        anfrage.add_header(k, v)
    return hole(anfrage)


def hole(anfrage):
    try:
        with urllib.request.urlopen(anfrage, context=ssl.create_default_context(), timeout=45) as a:
            text = a.read().decode(errors="replace")
            try:
                return a.status, json.loads(text)
            except ValueError:
                return a.status, {"_roh": text[:2000]}
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, {"_roh": text[:2000]}


def start(modus, datei):
    m = MODI[modus]
    schluessel, wert = m["feld"]
    status, antwort = post(m["devicecode"], {"client_id": m["client"], schluessel: wert})
    print(f"{modus}: HTTP {status}")
    if "device_code" not in antwort:
        print(json.dumps(antwort, indent=2)[:1200])
        return 1
    ziel = antwort.get("verification_uri") or antwort.get("verification_url")
    antwort["_modus"] = modus
    open(datei, "w").write(json.dumps(antwort))
    print(f">>> CODE: {antwort['user_code']}   auf   {ziel}")
    print(f"    gueltig {antwort.get('expires_in')} s, Zustand in {datei}")
    return 0


def warten(datei):
    z = json.load(open(datei))
    m = MODI[z["_modus"]]
    takt = int(z.get("interval", 5))
    ende = time.time() + int(z.get("expires_in", 900))
    felder = {
        "client_id": m["client"],
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        m["codefeld"]: z["device_code"],
    }
    while time.time() < ende:
        time.sleep(takt)
        status, antwort = post(m["token"], felder)
        if "access_token" in antwort:
            z.update(antwort)
            open(datei, "w").write(json.dumps(z))
            print(f"angemeldet (HTTP {status})")
            print("  scope:", antwort.get("scope"))
            print("  id_token:", "ja" if antwort.get("id_token") else "nein")
            print("  refresh_token:", "ja" if antwort.get("refresh_token") else "nein")
            return 0
        fehler = antwort.get("error")
        if fehler == "authorization_pending":
            continue
        if fehler == "slow_down":
            takt += 5
            continue
        print(f"HTTP {status}: {json.dumps(antwort)[:1200]}")
        return 1
    print("Zeit abgelaufen")
    return 1


def authz(datei):
    """Skypetoken holen. Privat nimmt purple-teams das id_token, nicht das
    access_token -- deshalb beide versuchen und sagen, welches traegt."""
    z = json.load(open(datei))
    m = MODI[z["_modus"]]
    for name in ("id_token", "access_token"):
        marke = z.get(name)
        if not marke:
            continue
        status, antwort = hole(_bearer(m["authz"], marke))
        print(f"== {m['authz']}  mit {name}: HTTP {status}")
        tokens = antwort.get("tokens") or antwort.get("skypeToken") or {}
        st = tokens.get("skypeToken") or tokens.get("skypetoken")
        if st:
            print("   skypeToken:", st[:40], "...")
            print("   expiresIn:", tokens.get("expiresIn"), " region:", antwort.get("region"))
            gtms = antwort.get("regionGtms") or {}
            if gtms:
                print("   regionGtms:", json.dumps(gtms)[:500])
            z["_skypetoken"] = st
            z["_chatsvc"] = m["chatsvc"] or gtms.get("chatService")
            open(datei, "w").write(json.dumps(z))
            return 0
        print("  ", json.dumps(antwort)[:600])
    return 1


def _bearer(url, marke):
    anfrage = urllib.request.Request(url, data=b"", method="POST")
    anfrage.add_header("Authorization", "Bearer " + marke)
    anfrage.add_header("Content-Type", "application/json")
    anfrage.add_header("Accept", "application/json; ver=1.0")
    return anfrage


def chats(datei):
    """Die Chatliste -- der eigentliche Beweis, dass der Weg traegt."""
    z = json.load(open(datei))
    basis = z.get("_chatsvc")
    st = z.get("_skypetoken")
    if not (basis and st):
        print("erst authz")
        return 1
    url = f"{basis}/v1/users/ME/conversations?view=msnp24Equivalent&pageSize=20"
    anfrage = urllib.request.Request(url)
    anfrage.add_header("Authentication", "skypetoken=" + st)
    anfrage.add_header("Accept", "application/json; ver=1.0")
    status, antwort = hole(anfrage)
    print(f"== {url}\n   HTTP {status}")
    gespraeche = antwort.get("conversations")
    if gespraeche is None:
        print("  ", json.dumps(antwort)[:900])
        return 1
    print(f"   {len(gespraeche)} Gespraeche")
    for g in gespraeche[:10]:
        letzte = (g.get("lastMessage") or {}).get("content", "")
        print(f"   - {g.get('id','?')[:48]:48}  {str(letzte)[:40]}")
    return 0


if __name__ == "__main__":
    was = sys.argv[1] if len(sys.argv) > 1 else "hilfe"
    if was == "start":
        modus = sys.argv[2] if len(sys.argv) > 2 else "privat"
        sys.exit(start(modus, sys.argv[3] if len(sys.argv) > 3 else f"/tmp/teams-{modus}.json"))
    elif was == "warten":
        sys.exit(warten(sys.argv[2]))
    elif was == "authz":
        sys.exit(authz(sys.argv[2]))
    elif was == "chats":
        sys.exit(chats(sys.argv[2]))
    else:
        print(__doc__)
