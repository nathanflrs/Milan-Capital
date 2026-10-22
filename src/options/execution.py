# src/options/execution.py
"""
Pièce 5 de la couche options : envoyer les ordres.

C'est la seule pièce du desk qui peut toucher au courtier. Elle est donc
construite autour d'une règle : **par défaut, elle ne transmet rien.**

Deux modes
----------
- **simulation** (par défaut) : chaque ordre est soumis à IBKR en
  `whatIfOrder`. IBKR calcule la marge et la commission, accepte ou refuse,
  et **rien n'est transmis au marché**.
- **réel** : l'ordre part. Seulement si `DESK_ENABLED=true` **et**
  `EXECUTION_ENABLED=true` dans l'environnement — deux verrous, plus le
  `ReadOnlyApi` d'IBC côté courtier (deploy/README.md). Le desk ne sera armé
  qu'à l'étape 7 du plan, après décision explicite.

Les ordres
----------
- **Iron butterfly** : un seul ordre combiné (BAG), donc jamais une jambe
  sans les autres. Convention IBKR : on *achète* la combinaison telle que
  définie, à un prix limite exprimé en débit — **négatif = on encaisse**.
  Paliers (protocole, section 2) : milieu de fourchette, puis trois pas vers
  le prix affiché, toutes les 2 minutes ; annulation au bout de 15 minutes.
- **MES** : ordre à cours limité « traversant » (2 échelons au-delà du
  meilleur prix), annulé s'il n'est pas exécuté en 60 secondes. Un ordre au
  marché pur pourrait être rempli à n'importe quel prix lors d'un trou de
  liquidité.

Tout ordre, simulé ou réel, laisse une ligne dans logs/desk/ordres.csv.

Pièges connus, verrouillés ici :
- sans `tif = "DAY"` explicite, IBKR répond par l'avertissement 10349 et
  `whatIfOrder` revient vide (docs/desk/etape1_instruments.md) ;
- les prix sont arrondis à 0,05 : multiple de tous les échelons d'options
  XSP, un prix hors échelon serait refusé.
"""
from __future__ import annotations

import csv
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

MODE_SIMULATION, MODE_REEL = "simulation", "reel"

ECHELON_COMBO = 0.05
ECHELON_MES = 0.25
PALIERS = 3
ATTENTE_PALIER_S = 120
DELAI_MAX_S = 900
DELAI_MES_S = 60
ROULEMENT_MES_JOURS = 7
JOURNAL = Path("logs/desk/ordres.csv")
COLONNES = ["horodatage", "mode", "instrument", "quantite", "prix_limite", "statut",
            "rempli", "prix_moyen", "commission", "marge_initiale", "detail"]


def mode_autorise(env=None) -> str:
    """'reel' seulement si les DEUX verrous sont ouverts ; sinon 'simulation'."""
    env = os.environ if env is None else env
    ouvert = lambda k: str(env.get(k, "false")).strip().lower() == "true"
    return MODE_REEL if ouvert("DESK_ENABLED") and ouvert("EXECUTION_ENABLED") else MODE_SIMULATION


def arrondir(prix: float, echelon: float, sens: str = "proche") -> float:
    """Arrondi à l'échelon : 'proche', 'haut' (payer plus) ou 'bas' (payer moins)."""
    n = prix / echelon
    n = {"proche": round, "haut": math.ceil, "bas": math.floor}[sens](round(n, 9))
    return round(n * echelon, 2)


def paliers(debit_milieu: float, debit_naturel: float, n: int = PALIERS,
            echelon: float = ECHELON_COMBO) -> List[float]:
    """Les prix limites successifs, en débit (négatif = crédit encaissé).

    Du milieu de fourchette jusqu'au prix affiché, en n pas. Le dernier palier
    est arrondi vers le haut : il doit être au moins aussi généreux que le prix
    affiché, sinon l'ordre resterait sans contrepartie.
    """
    prix = []
    for k in range(n + 1):
        p = debit_milieu + k / n * (debit_naturel - debit_milieu)
        p = arrondir(p, echelon, "haut" if k == n else "proche")
        if not prix or p != prix[-1]:
            prix.append(p)
    return prix


@dataclass
class Resultat:
    mode: str
    instrument: str
    quantite: int
    statut: str                       # 'simule', 'rempli', 'partiel', 'annule', 'refuse'
    rempli: int = 0
    prix_moyen: Optional[float] = None
    prix_limites: List[float] = field(default_factory=list)
    commission: Optional[float] = None
    marge_initiale: Optional[float] = None
    detail: str = ""


def journaliser(r: Resultat, chemin: Path = JOURNAL) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not chemin.exists()
    with chemin.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES)
        if nouveau:
            w.writeheader()
        w.writerow({
            "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": r.mode, "instrument": r.instrument, "quantite": r.quantite,
            "prix_limite": " → ".join(f"{p:g}" for p in r.prix_limites),
            "statut": r.statut, "rempli": r.rempli, "prix_moyen": r.prix_moyen,
            "commission": r.commission, "marge_initiale": r.marge_initiale,
            "detail": r.detail,
        })


def _nombre(x) -> Optional[float]:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or abs(x) > 1e300 else x


def _simuler(ib, contrat, ordre, r: Resultat) -> Resultat:
    erreurs: List[str] = []
    ecoute = lambda reqId, code, msg, c: erreurs.append(f"{code} {msg[:160]}") \
        if code not in (2104, 2106, 2107, 2158, 2119, 10167, 10090, 10091) else None
    ib.errorEvent += ecoute
    try:
        etat = ib.whatIfOrder(contrat, ordre)
    finally:
        ib.errorEvent -= ecoute
    if etat:
        r.statut = "simule"
        r.marge_initiale = _nombre(etat.initMarginChange)
        r.commission = _nombre(etat.commission) or _nombre(etat.maxCommission)
        r.detail = etat.warningText or ""
    else:
        r.statut = "refuse"
        r.detail = " | ".join(erreurs) or "aucune réponse d'IBKR"
    return r


def _attendre(ib, trade, jusqu_a: float, maintenant: Callable[[], float]) -> None:
    while not trade.isDone() and maintenant() < jusqu_a:
        ib.sleep(1)


def _remplissage(trade) -> Tuple[int, Optional[float], Optional[float]]:
    rempli = int(trade.orderStatus.filled or 0)
    prix = _nombre(trade.orderStatus.avgFillPrice) if rempli else None
    commission = sum(_nombre(f.commissionReport.commission) or 0.0
                     for f in getattr(trade, "fills", []) if f.commissionReport) or None
    return rempli, prix, commission


def executer_combo(ib, contrat, lots: int, prix: Sequence[float], mode: str, *,
                   instrument: str = "butterfly",
                   attente_palier: float = ATTENTE_PALIER_S, delai_max: float = DELAI_MAX_S,
                   maintenant: Callable[[], float] = time.monotonic,
                   journal: Optional[Path] = JOURNAL) -> Resultat:
    """Achète `lots` fois la combinaison, au premier palier puis aux suivants."""
    from ib_insync import LimitOrder

    r = Resultat(mode, instrument, lots, "refuse", prix_limites=list(prix))
    if lots <= 0 or not prix:
        r.detail = "rien à envoyer"
        return r
    ordre = LimitOrder("BUY", lots, prix[0])
    ordre.tif = "DAY"

    if mode != MODE_REEL:
        r = _simuler(ib, contrat, ordre, r)
    else:
        debut = maintenant()
        trade = ib.placeOrder(contrat, ordre)
        for i, p in enumerate(prix):
            if i:
                ordre.lmtPrice = p
                ib.placeOrder(contrat, ordre)          # même ordre : modification
            _attendre(ib, trade, min(debut + (i + 1) * attente_palier, debut + delai_max),
                      maintenant)
            if trade.isDone():
                break
        _attendre(ib, trade, debut + delai_max, maintenant)
        if not trade.isDone():
            ib.cancelOrder(ordre)
            ib.sleep(2)
        r.rempli, r.prix_moyen, r.commission = _remplissage(trade)
        r.statut = ("rempli" if r.rempli >= lots else "partiel" if r.rempli else "annule")
        r.detail = trade.orderStatus.status
    if journal:
        journaliser(r, journal)
    return r


# ── Construction des contrats ───────────────────────────────────────────────

def contrat_butterfly(ib, echeance: str, jambes: Sequence[Tuple[str, float, str]],
                      symbole: str = "XSP"):
    """Ordre combiné à partir de (type, strike, 'BUY'|'SELL') : une jambe par ligne."""
    from ib_insync import ComboLeg, Contract, Option

    options = [Option(symbole, echeance, k, t, "SMART", tradingClass=symbole)
               for t, k, _ in jambes]
    ib.qualifyContracts(*options)
    manquantes = [f"{t}{k:g}" for (t, k, _), o in zip(jambes, options) if not o.conId]
    if manquantes:
        raise ValueError(f"jambes introuvables chez IBKR : {', '.join(manquantes)}")
    legs = [ComboLeg(conId=o.conId, ratio=1, action=a, exchange="SMART")
            for o, (_, _, a) in zip(options, jambes)]
    return Contract(secType="BAG", symbol=symbole, currency="USD", exchange="SMART",
                    comboLegs=legs)


def jambes_ouverture(butterfly) -> List[Tuple[str, float, str]]:
    return [(j.type, j.strike, "BUY" if j.sens > 0 else "SELL") for j in butterfly.jambes]


def jambes_fermeture(butterfly) -> List[Tuple[str, float, str]]:
    """Les mêmes jambes, sens inversés : racheter ce qu'on a vendu, revendre les ailes."""
    return [(j.type, j.strike, "SELL" if j.sens > 0 else "BUY") for j in butterfly.jambes]


def choisir_mes(echeances: Sequence[str], aujourd_hui: date,
                roulement: int = ROULEMENT_MES_JOURS) -> str:
    """Le contrat MES le plus proche qui expire dans plus de `roulement` jours."""
    valides = sorted(e for e in echeances
                     if datetime.strptime(e[:8], "%Y%m%d").date() > aujourd_hui + timedelta(days=roulement))
    if not valides:
        raise ValueError("aucun contrat MES assez lointain")
    return valides[0]


def executer_mes(ib, n: int, mode: str, aujourd_hui: Optional[date] = None, *,
                 maintenant: Callable[[], float] = time.monotonic,
                 journal: Optional[Path] = JOURNAL) -> Optional[Resultat]:
    """Achète (n > 0) ou vend (n < 0) n micro-futures MES. Rien si n = 0."""
    from ib_insync import Future, LimitOrder

    if n == 0:
        return None
    aujourd_hui = aujourd_hui or date.today()
    details = ib.reqContractDetails(Future("MES", exchange="CME", currency="USD"))
    echeance = choisir_mes([d.contract.lastTradeDateOrContractMonth for d in details], aujourd_hui)
    contrat = next(d.contract for d in details if d.contract.lastTradeDateOrContractMonth == echeance)

    # Sans abonnement, IBKR ne renvoie rien tant qu'on n'a pas demandé le
    # différé (3). On le demande ici plutôt que de compter sur l'appelant :
    # le premier essai sur le serveur, le 2026-10-22, est revenu sans prix.
    ib.reqMarketDataType(int(os.getenv("OPTIONS_MARKET_DATA_TYPE", "3")))
    t = ib.reqMktData(contrat, "", False, False)
    ib.sleep(5)
    ib.cancelMktData(contrat)
    sens = "BUY" if n > 0 else "SELL"
    reference = (_nombre(t.ask if n > 0 else t.bid) or _nombre(t.last)
                 or _nombre(t.close))
    r = Resultat(mode, f"MES {echeance}", n, "refuse")
    if not reference:
        r.detail = "aucun prix MES"
    else:
        decalage = 2 * ECHELON_MES * (1 if n > 0 else -1)
        prix = arrondir(reference + decalage, ECHELON_MES, "haut" if n > 0 else "bas")
        r.prix_limites = [prix]
        ordre = LimitOrder(sens, abs(n), prix)
        ordre.tif = "DAY"
        if mode != MODE_REEL:
            r = _simuler(ib, contrat, ordre, r)
        else:
            debut = maintenant()
            trade = ib.placeOrder(contrat, ordre)
            _attendre(ib, trade, debut + DELAI_MES_S, maintenant)
            if not trade.isDone():
                ib.cancelOrder(ordre)
                ib.sleep(2)
            r.rempli, r.prix_moyen, r.commission = _remplissage(trade)
            r.statut = "rempli" if r.rempli >= abs(n) else "partiel" if r.rempli else "annule"
            r.detail = trade.orderStatus.status
    if journal:
        journaliser(r, journal)
    return r
