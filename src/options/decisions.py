# src/options/decisions.py
"""
Pièce 7a de la couche options : ce que le desk décide, à chaque contrôle.

Logique pure : l'état entre (registre, photo de chaîne, valeur liquidative,
date), une liste d'actions sort. Aucun ordre ne part d'ici — c'est
desk.py qui exécute. Séparer les deux permet de tester chaque décision du
desk sans courtier, jour par jour, cas par cas.

Règles : docs/desk/phase2_observation.md, section 2 et amendement 1.

Ordre des décisions à un contrôle :
    1. Middle Office    registre et courtier d'accord ? Sinon : rien.
    2. Volatility Trader  fermer les barreaux à 7 jours ou moins.
    3. Volatility Trader  10 h 30 : ouvrir le barreau de la semaine, s'il
                          n'existe pas et si la charte l'autorise.
    4. Execution Trader   couvrir l'exposition au-delà d'un MES — calculé
                          APRÈS exécution des étapes 2 et 3 (desk.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple, Union

import pandas as pd

from src.options import risque as rq
from src.options import structure as st
from src.options.greeks import grecques
from src.options.registre import Butterfly as Barreau
from src.options.registre import Livre

DTE_SORTIE = 7
LOTS_PAR_BARREAU = 1
BARREAUX_MAX_EN_REDUCTION = 2      # amendement 1 : « réduire » → pas de nouveau barreau au-delà
CONTROLE_OUVERTURE = "10:30"

VT, ET, MO, RM = "Volatility Trader", "Execution Trader", "Middle Office", "Risk Manager"


@dataclass(frozen=True)
class Fermer:
    barreau: Barreau
    debit_milieu: float
    debit_naturel: float


@dataclass(frozen=True)
class Ouvrir:
    butterfly: st.Butterfly
    lots: int
    # Le livre tel qu'il serait après l'ouverture : ce que le Risk Manager
    # relit et sur quoi il rejoue ses propres scénarios de stress.
    livre_apres: Optional[rq.Livre] = None
    vega_total_apres: float = 0.0


@dataclass
class Plan:
    actions: List[Union[Fermer, Ouvrir]] = field(default_factory=list)
    messages: List[Tuple[str, str]] = field(default_factory=list)   # (rôle, texte)
    bloque: bool = False

    def dire(self, role: str, texte: str) -> None:
        self.messages.append((role, texte))


# ── Prix des barreaux ouverts ──────────────────────────────────────────────

def _cotation(chaine: pd.DataFrame, echeance: str, type_: str, strike: float):
    ligne = chaine[(chaine["echeance"] == echeance) & (chaine["type"] == type_)
                   & (chaine["strike"] == strike)]
    if ligne.empty:
        return None
    l = ligne.iloc[0]
    if pd.isna(l["bid"]) or pd.isna(l["ask"]) or l["ask"] < l["bid"]:
        return None
    return l


def prix_fermeture(b: Barreau, chaine: pd.DataFrame) -> Optional[Tuple[float, float]]:
    """(débit au milieu, débit au prix affiché) pour fermer un barreau, par unité.

    Fermer = racheter le corps vendu (on paie l'ask) et revendre les ailes
    (on reçoit le bid). None si une jambe n'a pas de prix.
    """
    milieu = naturel = 0.0
    for t, k, sens in b.jambes:
        l = _cotation(chaine, b.echeance, t, k)
        if l is None:
            return None
        rachat = -sens                      # +1 : on rachète ; −1 : on revend
        milieu += rachat * (l["bid"] + l["ask"]) / 2
        naturel += rachat * (l["ask"] if rachat > 0 else l["bid"])
    return milieu, naturel


def delta_livre(livre: Livre, chaine: pd.DataFrame, spot: float, aujourd_hui: date,
                r: float = 0.04, q: float = 0.012) -> float:
    """Exposition au marché du livre, en unités XSP (MES = 50).

    Delta de chaque jambe lu dans la photo (celui d'IBKR) ; à défaut, recalculé
    par Black-Scholes avec la volatilité d'entrée du barreau.
    """
    total = sum(q_ * rq.UNITES_PAR_MES for q_ in livre.mes.values())
    for b in livre.barreaux:
        for t, k, sens in b.jambes:
            l = _cotation(chaine, b.echeance, t, k)
            d = None if l is None or pd.isna(l.get("delta")) else float(l["delta"])
            if d is None:
                d = grecques(spot, k, max(b.dte(aujourd_hui), 0) / 365, b.iv_atm, t, r, q).delta
            total += sens * b.lots * rq.MULT_OPTION * d
    return total


def _iv_jambe(chaine: Optional[pd.DataFrame], b: Barreau, t: str, k: float) -> float:
    """Volatilité implicite de la jambe elle-même, lue dans la photo.

    Les ailes n'ont pas la volatilité du centre (le « smile ») : réévaluer tout
    le barreau à la volatilité à la monnaie surestimait le vega et le stress du
    livre — écart repéré par le Risk Manager lors de sa première relecture
    réelle, le 2026-10-22 (164 $ par point au lieu de 139). À défaut de prix,
    la volatilité d'entrée du barreau.
    """
    if chaine is not None:
        l = _cotation(chaine, b.echeance, t, k)
        if l is not None and not pd.isna(l.get("vol_implicite")) and l["vol_implicite"] > 0:
            return float(l["vol_implicite"])
    return b.iv_atm


def _livre_risque(livre: Livre, extra: Optional[Barreau] = None,
                  chaine: Optional[pd.DataFrame] = None) -> rq.Livre:
    pos = [rq.Position("MES", q) for q in livre.mes.values()]
    for b in livre.barreaux + ([extra] if extra else []):
        pos += [rq.Position(t, s * b.lots, k, b.echeance, _iv_jambe(chaine, b, t, k))
                for t, k, s in b.jambes]
    return rq.Livre(pos)


# ── Les décisions ───────────────────────────────────────────────────────────

def planifier(livre: Livre, chaine: pd.DataFrame, spot: float, vl: float,
              aujourd_hui: date, moment: str, registre_ok: bool,
              ecarts: str = "") -> Plan:
    plan = Plan()

    # 1. Middle Office : sans accord avec le courtier, le desk ne décide rien.
    if not registre_ok:
        plan.bloque = True
        plan.dire(MO, f"Écart avec le courtier — desk suspendu, intervention humaine requise : {ecarts}")
        return plan
    plan.dire(MO, f"Registre et courtier d'accord : {len(livre.barreaux)} barreau(x), "
                  f"MES {sum(livre.mes.values()):+d}.")

    plus_haut = max(livre.plus_haut, vl)
    etat = rq.etat_baisse(vl, plus_haut)
    if etat != "normal":
        plan.dire(VT, f"Charte : baisse de {vl / plus_haut - 1:.1%} depuis le plus haut — état « {etat} ».")

    # 2. Sorties : tout barreau à 7 jours ou moins.
    for b in livre.barreaux:
        if b.dte(aujourd_hui) <= DTE_SORTIE:
            prix = prix_fermeture(b, chaine)
            if prix is None:
                plan.dire(VT, f"Barreau {b.echeance} à {b.dte(aujourd_hui)} j : prix incomplets, "
                              f"fermeture au prochain contrôle.")
            else:
                plan.actions.append(Fermer(b, *prix))
                plan.dire(VT, f"Fermeture du barreau {b.echeance} ({b.dte(aujourd_hui)} j) : "
                              f"débit {prix[0]:.2f} au milieu, crédit d'entrée {b.credit:.2f}.")

    # 3. Ouverture : une fois par semaine, au contrôle de 10 h 30.
    if moment != CONTROLE_OUVERTURE:
        return plan
    semaine = aujourd_hui.isocalendar()[:2]
    if any(date.fromisoformat(b.ouvert_le).isocalendar()[:2] == semaine for b in livre.barreaux):
        plan.dire(VT, "Barreau de la semaine déjà ouvert.")
        return plan
    restants = [b for b in livre.barreaux if not any(
        isinstance(a, Fermer) and a.barreau is b for a in plan.actions)]
    if etat == "arret":
        plan.dire(VT, "Charte : desk à l'arrêt, aucun nouveau barreau.")
        return plan
    if etat == "reduire" and len(restants) >= BARREAUX_MAX_EN_REDUCTION:
        plan.dire(VT, f"Charte : réduction, pas de nouveau barreau au-delà de "
                      f"{BARREAUX_MAX_EN_REDUCTION}.")
        return plan

    try:
        b = st.construire(chaine, spot, aujourd_hui)
    except st.PasDeButterfly as e:
        plan.dire(VT, f"Pas de barreau cette fois : {e}.")
        return plan
    nouveau = Barreau(b.echeance, b.aile_put, b.centre, b.aile_call, LOTS_PAR_BARREAU,
                      aujourd_hui.isoformat(), b.credit_milieu, b.vega_lot,
                      b.perte_max_lot, b.iv_atm)
    apres = Livre(barreaux=restants, mes=dict(livre.mes))
    risque = _livre_risque(apres, nouveau, chaine)
    ctrl = rq.controler_ouverture(risque, b.perte_max_lot * LOTS_PAR_BARREAU, spot,
                                  aujourd_hui, vl, plus_haut)
    raisons = list(ctrl.raisons)
    vega_total = abs(risque.vega_dollars(spot, aujourd_hui))
    if vega_total > st.VEGA_CIBLE * vl:
        raisons.append(f"vega du livre {vega_total:,.0f} $ par point > taille testée "
                       f"{st.VEGA_CIBLE * vl:,.0f} $")
    if raisons:
        plan.dire(VT, "Barreau refusé par la charte : " + " ; ".join(raisons) + ".")
        return plan

    plan.actions.append(Ouvrir(b, LOTS_PAR_BARREAU, risque, vega_total))
    plan.dire(VT, f"Ouverture du barreau {b.echeance} ({b.dte} j) : "
                  f"{b.aile_put:g}/{b.centre:g}/{b.aile_call:g}, crédit {b.credit_milieu:.2f} "
                  f"au milieu, perte max {b.perte_max_lot:,.0f} $, stress livre "
                  f"{risque.stress(spot, aujourd_hui):,.0f} $.")
    return plan


def couverture(livre: Livre, chaine: pd.DataFrame, spot: float,
               aujourd_hui: date) -> Tuple[int, float, str]:
    """(MES à trader, exposition avant, message de l'Execution Trader)."""
    d = delta_livre(livre, chaine, spot, aujourd_hui)
    n = rq.mes_a_trader(d)
    if n == 0:
        return 0, d, f"Exposition {d:+.0f} unités, sous le seuil d'un MES : pas de couverture."
    return n, d, f"Exposition {d:+.0f} unités : {'achat' if n > 0 else 'vente'} de {abs(n)} MES."
