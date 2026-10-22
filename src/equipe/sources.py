# src/equipe/sources.py
"""
Les sources du Research Analyst : ce que le code va chercher, avant que
Claude ne lise.

Choix de Nathan (docs/desk/equipe.md, règle 5) : sources officielles et sites
financiers sérieux, fixés ici. Flux testés depuis le serveur le 2026-10-22 —
CNBC (403 depuis l'adresse du serveur) et Yahoo Finance (404) écartés.

Rien ici n'appelle Claude : ce sont des données, lues par le code, qui seront
présentées aux membres comme telles.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import socket
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

FLUX: Dict[str, str] = {
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "BLS": "https://www.bls.gov/feed/bls_latest.rss",
    "BEA": "https://apps.bea.gov/rss/rss.xml",
    "Maison-Blanche": "https://www.whitehouse.gov/news/feed/",
    "SEC": "https://www.sec.gov/news/pressreleases.rss",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "MarketWatch flash": "https://feeds.content.dowjones.io/public/rss/mw_bulletins",
    "WSJ marchés": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
}

# Recherche web du Research Analyst : seulement ces domaines.
DOMAINES = ["federalreserve.gov", "bls.gov", "bea.gov", "treasury.gov", "sec.gov",
            "whitehouse.gov", "cboe.com", "cmegroup.com", "cnbc.com", "bloomberg.com"]

# Refusés par la recherche web d'Anthropic (« not accessible to our user
# agent », 400 au premier briefing réel, 2026-10-22) : ces sites bloquent son
# robot. MarketWatch et le WSJ restent lus par NOTRE code via leurs flux
# publics (FLUX ci-dessus).
DOMAINES_REFUSES = ["apnews.com", "ft.com", "marketwatch.com", "reuters.com", "wsj.com"]

CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
AGENT = "Mozilla/5.0 MilanCapital/1.0"


def empreinte(source: str, titre: str) -> str:
    return hashlib.sha1(f"{source}|{titre.strip().lower()}".encode()).hexdigest()[:16]


def titres(depuis: Optional[datetime] = None, flux: Dict[str, str] = FLUX,
           parse=None) -> List[dict]:
    """Les titres publiés depuis `depuis` (UTC), toutes sources, du plus récent au plus ancien.

    Un flux en panne est noté et ignoré : la veille continue avec les autres.
    """
    import feedparser

    parse = parse or (lambda url: feedparser.parse(url, agent=AGENT))
    socket.setdefaulttimeout(15)
    sortie = []
    for source, url in flux.items():
        try:
            f = parse(url)
        except Exception as e:
            sortie.append({"source": source, "erreur": str(e)[:120]})
            continue
        for e in f.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            publie = datetime(*t[:6], tzinfo=timezone.utc) if t else None
            if depuis and publie and publie < depuis:
                continue
            titre = (e.get("title") or "").strip()
            if not titre:
                continue
            sortie.append({"source": source, "titre": titre,
                           "resume": (e.get("summary") or "")[:300],
                           "lien": e.get("link", ""),
                           "publie_utc": publie.isoformat() if publie else None,
                           "id": empreinte(source, titre)})
    return sorted([s for s in sortie if "titre" in s],
                  key=lambda s: s["publie_utc"] or "", reverse=True) + \
        [s for s in sortie if "erreur" in s]


def volatilite_cboe(indices=("VIX9D", "VIX", "VIX3M"), jours: int = 10, lire=None) -> dict:
    """Derniers niveaux des indices de volatilité du CBOE (clôtures, fichiers du CBOE).

    VIX9D, VIX et VIX3M donnent la structure par terme : une courbe inversée
    (court au-dessus du long) signale un stress en cours.
    """
    def defaut(url):
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode()

    lire = lire or defaut
    sortie = {}
    for i in indices:
        try:
            lignes = list(csv.DictReader(io.StringIO(lire(CBOE.format(i)))))[-jours:]
            col = "CLOSE" if "CLOSE" in lignes[-1] else i
            sortie[i] = [{"date": l["DATE"], "cloture": float(l[col])} for l in lignes]
        except Exception as e:
            sortie[i] = f"indisponible : {e}"
    try:
        v9, v, v3 = (sortie[k][-1]["cloture"] for k in ("VIX9D", "VIX", "VIX3M"))
        sortie["structure"] = ("inversée (stress)" if v9 > v or v > v3 else "normale (contango)")
    except Exception:
        pass
    return sortie


def etat_du_desk(livre_chemin: Path = Path("logs/desk/livre.json")) -> dict:
    """Ce que le desk détient : barreaux, échéances, MES (registre du Middle Office)."""
    if not livre_chemin.exists():
        return {"barreaux": [], "mes": {}, "note": "Aucun barreau ouvert (registre vide)."}
    d = json.loads(livre_chemin.read_text())
    return {"barreaux": [{k: b[k] for k in ("echeance", "aile_put", "centre", "aile_call", "lots",
                                            "ouvert_le")} for b in d.get("barreaux", [])],
            "mes": d.get("mes", {})}
