# src/prop/ordres.py
"""
Les ordres du prop trader : entrer, protéger, sortir, déplacer.

Comme pour le desk (src/options/execution.py), **par défaut rien ne part** :
le mode réel exige `PROP_ENABLED=true` **et** `EXECUTION_ENABLED=true`. En
simulation, l'entrée est soumise à IBKR en whatIf (marge, commission,
acceptation), et rien d'autre ne bouge.

Les ordres, en réel
-------------------
- **Entrée** : ordre limite au prix du plan, valable 3 minutes ; le reste
  non exécuté est annulé.
- **Protection**, aussitôt sur la quantité réellement exécutée : un stop et
  un objectif chez IBKR, en un groupe OCA (l'un annule l'autre), valables
  jusqu'à annulation. Ils travaillent seuls entre les passages ; leur
  référence d'ordre, « prop:<id>:stop » ou « prop:<id>:objectif », permet au
  registre de reconnaître leur exécution.
- **Sortie** décidée en séance : on retire la protection, puis ordre limite
  « traversant » (0,5 % au-delà du cours), 60 secondes. Ce qui n'est pas
  sorti est aussitôt reprotégé.

Tout ordre laisse une ligne dans logs/prop/ordres.csv.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from src.options import execution as ex
from src.options.execution import MODE_REEL, MODE_SIMULATION, Resultat

JOURNAL = Path("logs/prop/ordres.csv")
DELAI_ENTREE_S = 180
DELAI_SORTIE_S = 60
TRAVERSEE = 0.005


def mode_autorise(env=None) -> str:
    """'reel' seulement si PROP_ENABLED et EXECUTION_ENABLED sont tous deux ouverts."""
    env = os.environ if env is None else env
    ouvert = lambda k: str(env.get(k, "false")).strip().lower() == "true"
    return MODE_REEL if ouvert("PROP_ENABLED") and ouvert("EXECUTION_ENABLED") else MODE_SIMULATION


def symbole_ibkr(ticker: str) -> str:
    """BRK-B (collecte) → « BRK B » (IBKR)."""
    return ticker.replace("-", " ")


def cent(prix: float, sens: str = "proche") -> float:
    return ex.arrondir(prix, 0.01, sens)


def contrats(ib, tickers: Iterable[str]) -> Dict[str, object]:
    from ib_insync import Stock
    sortie = {}
    for t in tickers:
        c = Stock(symbole_ibkr(t), "SMART", "USD")
        ib.qualifyContracts(c)
        if c.conId:
            sortie[t] = c
    return sortie


def cours(ib, tickers: List[str], attente: float = 4.0) -> Dict[str, float]:
    """Derniers cours (différés de 15 minutes sans abonnement) : dernier, sinon milieu, sinon clôture."""
    if not tickers:
        return {}
    ib.reqMarketDataType(int(os.getenv("OPTIONS_MARKET_DATA_TYPE", "3")))
    cs = contrats(ib, tickers)
    lignes = {t: ib.reqMktData(c, "", False, False) for t, c in cs.items()}
    ib.sleep(attente)
    sortie = {}
    for t, l in lignes.items():
        ib.cancelMktData(cs[t])
        bid, ask = ex._nombre(l.bid), ex._nombre(l.ask)
        milieu = (bid + ask) / 2 if bid and ask and bid > 0 and ask >= bid else None
        p = ex._nombre(l.last) or milieu or ex._nombre(l.close)
        if p and p > 0:
            sortie[t] = round(p, 2)
    return sortie


def _action(sens: int, sortie: bool = False) -> str:
    achete = (sens > 0) != sortie
    return "BUY" if achete else "SELL"


def _attendre(ib, trade, delai: float, maintenant: Callable[[], float]) -> None:
    fin = maintenant() + delai
    while not trade.isDone() and maintenant() < fin:
        ib.sleep(1)


def entrer(ib, contrat, id_: str, sens: int, quantite: int, limite: float, mode: str, *,
           delai: float = DELAI_ENTREE_S, maintenant: Callable[[], float] = time.monotonic,
           journal: Optional[Path] = JOURNAL) -> Resultat:
    from ib_insync import LimitOrder

    r = Resultat(mode, f"{contrat.symbol} entrée", sens * quantite, "refuse", prix_limites=[limite])
    ordre = LimitOrder(_action(sens), quantite, limite)
    ordre.tif = "DAY"
    ordre.orderRef = f"prop:{id_}:entree"
    if mode != MODE_REEL:
        r = ex._simuler(ib, contrat, ordre, r)
    else:
        trade = ib.placeOrder(contrat, ordre)
        _attendre(ib, trade, delai, maintenant)
        if not trade.isDone():
            ib.cancelOrder(ordre)
            ib.sleep(2)
        r.rempli, r.prix_moyen, r.commission = ex._remplissage(trade)
        r.statut = "rempli" if r.rempli >= quantite else "partiel" if r.rempli else "annule"
        r.detail = trade.orderStatus.status
    if journal:
        ex.journaliser(r, journal)
    return r


def proteger(ib, contrat, id_: str, sens: int, quantite: int, stop: float, objectif: float, *,
             journal: Optional[Path] = JOURNAL) -> Tuple[object, object]:
    """Stop et objectif chez IBKR, un groupe OCA, valables jusqu'à annulation (réel seulement)."""
    from ib_insync import LimitOrder, StopOrder

    action = _action(sens, sortie=True)
    groupe = f"prop-{id_}-{int(time.time())}"
    o_stop = StopOrder(action, quantite, cent(stop))
    o_obj = LimitOrder(action, quantite, cent(objectif))
    for o, nom in ((o_stop, "stop"), (o_obj, "objectif")):
        o.tif = "GTC"
        o.ocaGroup, o.ocaType = groupe, 1          # 1 : l'exécution de l'un annule l'autre
        o.orderRef = f"prop:{id_}:{nom}"
    t_stop, t_obj = ib.placeOrder(contrat, o_stop), ib.placeOrder(contrat, o_obj)
    ib.sleep(2)
    if journal:
        for o, t, nom in ((o_stop, t_stop, "stop"), (o_obj, t_obj, "objectif")):
            ex.journaliser(Resultat(MODE_REEL, f"{contrat.symbol} {nom}", -sens * quantite, "pose",
                                    prix_limites=[o.auxPrice if nom == "stop" else o.lmtPrice],
                                    detail=t.orderStatus.status), journal)
    return t_stop, t_obj


def protection(ib, id_: str) -> Dict[str, object]:
    """Les ordres de protection encore actifs d'une position : {'stop': trade, 'objectif': trade}."""
    ib.reqAllOpenOrders()
    ib.sleep(1)
    sortie = {}
    for t in ib.openTrades():
        ref = t.order.orderRef or ""
        if ref.startswith(f"prop:{id_}:") and not t.isDone():
            sortie[ref.split(":")[2]] = t
    return sortie


def retirer_protection(ib, id_: str) -> int:
    trades = protection(ib, id_)
    for t in trades.values():
        ib.cancelOrder(t.order)
    if trades:
        ib.sleep(3)
    return len(trades)


def deplacer(ib, id_: str, quoi: str, prix: float, *, journal: Optional[Path] = JOURNAL) -> bool:
    """Modifie le stop ('stop') ou l'objectif ('objectif') déjà posé chez IBKR."""
    t = protection(ib, id_).get(quoi)
    if t is None:
        return False
    if quoi == "stop":
        t.order.auxPrice = cent(prix)
    else:
        t.order.lmtPrice = cent(prix)
    ib.placeOrder(t.contract, t.order)                # même ordre : modification
    ib.sleep(2)
    if journal:
        ex.journaliser(Resultat(MODE_REEL, f"{t.contract.symbol} {quoi} déplacé", 0, "modifie",
                                prix_limites=[cent(prix)], detail=t.orderStatus.status), journal)
    return True


def sortir(ib, contrat, id_: str, sens: int, quantite: int, dernier: float, *,
           delai: float = DELAI_SORTIE_S, maintenant: Callable[[], float] = time.monotonic,
           journal: Optional[Path] = JOURNAL) -> Resultat:
    """Sortie décidée en séance (réel seulement). L'appelant reprotège ce qui reste."""
    from ib_insync import LimitOrder

    retirer_protection(ib, id_)
    limite = cent(dernier * (1 - TRAVERSEE * sens), "bas" if sens > 0 else "haut")
    ordre = LimitOrder(_action(sens, sortie=True), quantite, limite)
    ordre.tif = "DAY"
    ordre.orderRef = f"prop:{id_}:sortie"
    r = Resultat(MODE_REEL, f"{contrat.symbol} sortie", -sens * quantite, "refuse", prix_limites=[limite])
    trade = ib.placeOrder(contrat, ordre)
    _attendre(ib, trade, delai, maintenant)
    if not trade.isDone():
        ib.cancelOrder(ordre)
        ib.sleep(2)
    r.rempli, r.prix_moyen, r.commission = ex._remplissage(trade)
    r.statut = "rempli" if r.rempli >= quantite else "partiel" if r.rempli else "annule"
    r.detail = trade.orderStatus.status
    if journal:
        ex.journaliser(r, journal)
    return r
