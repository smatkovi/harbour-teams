#!/usr/bin/env python3
"""Der Teil von `requests`, den teams_api.py wirklich benutzt -- auf urllib.

Warum das hier steht: `python3-requests` ist auf Sailfish nicht installiert,
und was mit `pip --user` daneben liegt, sieht die App im Sandkasten nicht
(~/.local/lib ist dort unsichtbar). Ein fehlgeschlagenes `import requests`
reisst unter PyOtherSide nicht nur die Zeile, sondern das ganze Modul mit --
die App startet dann gar nicht.

Nachgebaut ist genau die benutzte Oberflaeche, nicht mehr:

    get/post/put/delete(url, headers=, params=, json=, data=, timeout=,
                        stream=, allow_redirects=)
    Antwort: .status_code  .text  .content  .headers  .json()
             .raise_for_status()  .iter_content(n)

Absichtlich *nicht* nachgebaut: Sitzungen, Kekse, Wiederholungen,
Umleitungszaehlung. Wer mehr braucht, soll es hier ergaenzen und nicht
anderswo an requests vorbeiprogrammieren.
"""

import gzip
import json as _json
import ssl
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["get", "post", "put", "delete", "request", "Antwort", "RequestException"]


class RequestException(Exception):
    """Entspricht requests.RequestException -- teams_api faengt breit."""


class HTTPError(RequestException):
    pass


class Antwort:
    """Was die Aufrufer von einer requests-Antwort anfassen."""

    def __init__(self, status_code, inhalt, kopfzeilen, url):
        self.status_code = status_code
        self.content = inhalt
        self.headers = kopfzeilen
        self.url = url

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return _json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code} fuer {self.url}")

    def iter_content(self, chunk_size=8192):
        """Der Inhalt liegt schon ganz da; stueckweise ist hier nur Form.

        Grosse Dateien gehen damit durch den Arbeitsspeicher. Das ist der
        Preis dafuer, dass die App ueberhaupt laeuft; wenn es stoert, gehoert
        hier ein echter Datenstrom hin.
        """
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]


def _zusammenbauen(url, params):
    if not params:
        return url
    teile = urllib.parse.urlsplit(url)
    vorhanden = urllib.parse.parse_qsl(teile.query, keep_blank_values=True)
    for schluessel, wert in (params.items() if isinstance(params, dict) else params):
        if wert is None:
            continue
        vorhanden.append((schluessel, str(wert)))
    return urllib.parse.urlunsplit(teile._replace(query=urllib.parse.urlencode(vorhanden)))


def request(method, url, headers=None, params=None, json=None, data=None,
            timeout=45, stream=False, allow_redirects=True):
    kopf = dict(headers or {})
    koerper = None

    if json is not None:
        koerper = _json.dumps(json).encode("utf-8")
        kopf.setdefault("Content-Type", "application/json")
    elif data is not None:
        if isinstance(data, (bytes, bytearray)):
            koerper = bytes(data)
        elif isinstance(data, str):
            koerper = data.encode("utf-8")
        else:
            koerper = urllib.parse.urlencode(data).encode("utf-8")
            kopf.setdefault("Content-Type", "application/x-www-form-urlencoded")

    # Gezippt antworten lassen: auf 2G ist das der Unterschied zwischen
    # zaeh und brauchbar. Wir packen selbst aus.
    kopf.setdefault("Accept-Encoding", "gzip")

    anfrage = urllib.request.Request(
        _zusammenbauen(url, params), data=koerper, headers=kopf, method=method.upper())

    aufbauer = [urllib.request.HTTPSHandler(context=ssl.create_default_context())]
    if not allow_redirects:
        aufbauer.append(_KeineUmleitung())
    oeffner = urllib.request.build_opener(*aufbauer)

    try:
        antwort = oeffner.open(anfrage, timeout=timeout)
    except urllib.error.HTTPError as e:
        # Ein Fehlerschluss ist bei requests keine Ausnahme, sondern eine
        # Antwort mit status_code -- und teams_api prueft genau den.
        antwort = e
    except urllib.error.URLError as e:
        raise RequestException(str(e.reason)) from e
    except OSError as e:
        raise RequestException(str(e)) from e

    with antwort:
        inhalt = antwort.read()
        kopfzeilen = _Kopfzeilen(antwort.headers)
        if kopfzeilen.get("Content-Encoding", "").lower() == "gzip":
            try:
                inhalt = gzip.decompress(inhalt)
            except OSError:
                pass  # doch nicht gezippt
        status = getattr(antwort, "status", None) or antwort.getcode()
        return Antwort(status, inhalt, kopfzeilen, antwort.geturl())


class _KeineUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _Kopfzeilen(dict):
    """Kopfzeilen ohne Ruecksicht auf Gross- und Kleinschreibung."""

    def __init__(self, nachricht):
        super().__init__()
        for schluessel, wert in nachricht.items():
            self[schluessel.lower()] = wert

    def get(self, schluessel, vorgabe=None):
        return super().get(str(schluessel).lower(), vorgabe)

    def __getitem__(self, schluessel):
        return super().__getitem__(str(schluessel).lower())

    def __contains__(self, schluessel):
        return super().__contains__(str(schluessel).lower())


def get(url, **k):
    return request("GET", url, **k)


def post(url, **k):
    return request("POST", url, **k)


def put(url, **k):
    return request("PUT", url, **k)


def delete(url, **k):
    return request("DELETE", url, **k)
