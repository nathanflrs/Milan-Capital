# src/options/collect.py
"""
Collecteur quotidien des chaînes d'options SPY et XSP (étape 2 du plan).

    python -m src.options.collect [--symboles SPY XSP] [--sortie logs/options_chain]

Pourquoi
--------
L'historique de prix d'options (OptionMetrics) ne nous est pas accessible. On
construit donc le nôtre : chaque jour de bourse, une photo de la chaîne près
de la clôture — prix, volatilité implicite, grecques. Chaque jour collecté est
une donnée à nous ; un jour raté est perdu pour toujours, d'où le minuteur
quotidien et le journal qui signale les trous.

SPY et XSP côte à côte : le desk visera probablement XSP (réglé en cash,
exercice européen, même indice que le VIX — docs/desk/etape1_instruments.md),
mais XSP est moins échangé. Comparer leurs écarts achat-vente sur les mêmes
jours tranchera.

Ce que la photo contient, et ce qu'elle ne contient pas
-------------------------------------------------------
- Échéances : les vendredis entre 7 et 60 jours. Le desk vend à ~30 jours ;
  les échéances quotidiennes multiplieraient le volume sans rien apporter.
- Prix d'exercice : tous ceux à ±3 % du cours, puis un sur cinq points
  jusqu'à ±12 % — là où vivent le straddle vendu et ses ailes.
- Les prix arrivent **en différé de 15 minutes** tant qu'aucun abonnement
  OPRA n'existe (compte d'essai). Le minuteur tourne à 15 h 45 à New York :
  la photo montre donc le marché vers 15 h 30, liquide et proche de la clôture.

Garanties
---------
1. **Lecture seule.** Connexion `readonly=True` : aucun ordre ne peut partir.
2. **Rien d'écrit à moitié.** Le fichier du jour est écrit à côté puis
   renommé.
3. **Ce qui manque est chiffré.** Le journal note, par symbole, combien de
   contrats ont un prix et des grecques. Un jour férié se voit : aucun prix.
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd

SORTIE = Path("logs/options_chain")
JOURNAL = SORTIE / "journal.csv"
COLONNES_JOURNAL = ["date", "symbole", "spot", "echeances", "contrats",
                    "avec_prix", "avec_grecques", "duree_s", "type_donnees"]

DTE_MIN, DTE_MAX = 7, 60
ZONE_FINE = 0.03          # tous les prix d'exercice à ±3 %
ZONE_LARGE = 0.12         # puis un sur PAS_LARGE jusqu'à ±12 %
PAS_LARGE = 5
LOT = 80                  # lignes de marché simultanées (limite IBKR : 100)
ATTENTE_LOT = 6.0         # secondes pour que prix et grecques arrivent
CLIENT_ID = int(os.getenv("OPTIONS_CLIENT_ID", "21"))

# Où chercher chaque sous-jacent. XSP est un indice, SPY un ETF.
SOUS_JACENTS = {
    "SPY": {"secType": "STK", "exchange": "SMART"},
    "XSP": {"secType": "IND", "exchange": "CBOE"},
}


def _nombre(x) -> Optional[float]:
    """Les prix IBKR absents valent NaN ou -1 : on les ramène à None."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or x < 0:
        return None
    return x


def choisir_echeances(echeances: Iterable[str], aujourd_hui: date,
                      dte_min: int = DTE_MIN, dte_max: int = DTE_MAX) -> List[str]:
    """Les vendredis entre dte_min et dte_max jours, au format AAAAMMJJ."""
    retenues = []
    for e in sorted(set(echeances)):
        d = datetime.strptime(e, "%Y%m%d").date()
        if d.weekday() == 4 and dte_min <= (d - aujourd_hui).days <= dte_max:
            retenues.append(e)
    return retenues


def choisir_strikes(strikes: Iterable[float], spot: float) -> List[float]:
    """Tous les prix d'exercice proches, puis un sur PAS_LARGE plus loin."""
    retenus = []
    for k in sorted(set(strikes)):
        # Arrondi : 97 / 100 − 1 vaut 0,0300000000000000027 en virgule
        # flottante, et sortait de la zone fine pile à sa frontière.
        ecart = round(abs(k / spot - 1), 9)
        if ecart <= ZONE_FINE:
            retenus.append(k)
        elif ecart <= ZONE_LARGE and float(k).is_integer() and int(k) % PAS_LARGE == 0:
            retenus.append(k)
    return retenus


def ligne(symbole: str, spot: float, contrat, ticker, horodatage: str,
          aujourd_hui: date) -> dict:
    """Une ligne de la photo : le contrat, ses prix, ses grecques."""
    g = getattr(ticker, "modelGreeks", None)
    echeance = datetime.strptime(contrat.lastTradeDateOrContractMonth, "%Y%m%d").date()
    return {
        "horodatage": horodatage,
        "symbole": symbole,
        "spot": spot,
        "echeance": contrat.lastTradeDateOrContractMonth,
        "dte": (echeance - aujourd_hui).days,
        "strike": float(contrat.strike),
        "type": contrat.right,
        "conid": int(contrat.conId),
        "bid": _nombre(ticker.bid),
        "ask": _nombre(ticker.ask),
        "bid_size": _nombre(ticker.bidSize),
        "ask_size": _nombre(ticker.askSize),
        "dernier": _nombre(ticker.last),
        "cloture_veille": _nombre(ticker.close),
        "volume": _nombre(ticker.volume),
        "vol_implicite": _nombre(g.impliedVol) if g else None,
        "delta": (float(g.delta) if g and g.delta is not None
                  and not math.isnan(g.delta) else None),
        "gamma": _nombre(g.gamma) if g else None,
        "vega": _nombre(g.vega) if g else None,
        "theta": (float(g.theta) if g and g.theta is not None
                  and not math.isnan(g.theta) else None),
        "prix_modele": _nombre(g.optPrice) if g else None,
        "sous_jacent_modele": _nombre(g.undPrice) if g else None,
    }


def _ecrire_journal(rangee: dict, chemin: Path = JOURNAL) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not chemin.exists()
    with chemin.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_JOURNAL)
        if nouveau:
            w.writeheader()
        w.writerow(rangee)


def _ecrire(df: pd.DataFrame, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_suffix(".tmp")
    df.to_parquet(provisoire, index=False)
    provisoire.replace(chemin)


def _cours(ib, contrat) -> Optional[float]:
    t = ib.reqMktData(contrat, "", False, False)
    ib.sleep(4)
    ib.cancelMktData(contrat)
    for x in (t.last, t.marketPrice(), t.close):
        x = _nombre(x)
        if x:
            return x
    return None


def collecter_symbole(ib, symbole: str, aujourd_hui: date,
                      journal: Path = JOURNAL) -> pd.DataFrame:
    from ib_insync import Contract, Option

    debut = time.time()
    sj = Contract(symbol=symbole, currency="USD", **SOUS_JACENTS[symbole])
    ib.qualifyContracts(sj)
    spot = _cours(ib, sj)
    if not spot:
        raise RuntimeError(f"{symbole} : aucun cours — marché fermé ?")

    chaines = [c for c in ib.reqSecDefOptParams(sj.symbol, "", sj.secType, sj.conId)
               if c.tradingClass == symbole]       # écarte 2SPY & co.
    if not chaines:
        raise RuntimeError(f"{symbole} : aucune chaîne d'options")
    chaine = next((c for c in chaines if c.exchange == "SMART"), chaines[0])

    echeances = choisir_echeances(chaine.expirations, aujourd_hui)
    strikes = choisir_strikes(chaine.strikes, spot)
    candidats = [Option(symbole, e, k, droit, "SMART", tradingClass=symbole)
                 for e in echeances for k in strikes for droit in ("P", "C")]
    # Toutes les combinaisons échéance × prix d'exercice n'existent pas :
    # celles qu'IBKR ne reconnaît pas restent à conId 0 et sont écartées.
    qualifies = [c for c in ib.qualifyContracts(*candidats) if c.conId]

    horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lignes = []
    for i in range(0, len(qualifies), LOT):
        lot = qualifies[i:i + LOT]
        tickers = [ib.reqMktData(c, "", False, False) for c in lot]
        ib.sleep(ATTENTE_LOT)
        for c, t in zip(lot, tickers):
            lignes.append(ligne(symbole, spot, c, t, horodatage, aujourd_hui))
            ib.cancelMktData(c)

    df = pd.DataFrame(lignes)
    _ecrire_journal({
        "date": aujourd_hui.isoformat(), "symbole": symbole, "spot": spot,
        "echeances": len(echeances), "contrats": len(df),
        "avec_prix": int((df["bid"].notna() & df["ask"].notna()).sum()) if len(df) else 0,
        "avec_grecques": int(df["vol_implicite"].notna().sum()) if len(df) else 0,
        "duree_s": round(time.time() - debut, 1),
        "type_donnees": "différé" if os.getenv("OPTIONS_MARKET_DATA_TYPE", "3") == "3" else "direct",
    }, journal)
    return df


def run(symboles: Sequence[str] = ("SPY", "XSP"), sortie: Path = SORTIE,
        aujourd_hui: Optional[date] = None) -> int:
    from ib_insync import IB

    aujourd_hui = aujourd_hui or date.today()
    # ib_insync journalise chaque contrat inexistant (erreur 200) et chaque
    # avertissement « données différées » (10090) : plus de mille lignes par
    # passage, qui noieraient le journal. Ce qui manque est déjà chiffré dans
    # journal.csv.
    logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
    ib = IB()
    ib.RequestTimeout = 120
    ib.connect(os.getenv("IBKR_HOST", "127.0.0.1"), int(os.getenv("IBKR_PORT", "4002")),
               clientId=CLIENT_ID, readonly=True)
    # 3 = différé, qui bascule de lui-même en direct si un abonnement existe.
    ib.reqMarketDataType(int(os.getenv("OPTIONS_MARKET_DATA_TYPE", "3")))
    echecs = 0
    try:
        for s in symboles:
            try:
                df = collecter_symbole(ib, s, aujourd_hui, sortie / "journal.csv")
                _ecrire(df, sortie / aujourd_hui.isoformat() / f"{s}.parquet")
                avec_prix = int((df["bid"].notna() & df["ask"].notna()).sum())
                print(f"{s} : {len(df)} contrats, {avec_prix} avec prix, "
                      f"{int(df['vol_implicite'].notna().sum())} avec grecques")
            except Exception as e:      # un symbole raté n'empêche pas l'autre
                echecs += 1
                print(f"{s} : ÉCHEC — {e}", file=sys.stderr)
    finally:
        ib.disconnect()
    return 1 if echecs else 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--symboles", nargs="+", default=["SPY", "XSP"])
    p.add_argument("--sortie", type=Path, default=SORTIE)
    a = p.parse_args(argv)
    return run(a.symboles, a.sortie)


if __name__ == "__main__":
    sys.exit(main())
