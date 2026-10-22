# src/equipe/contexte.py
"""
Ce que le Risk Manager voit d'une séance : un instantané chiffré, figé au
moment de la proposition. Logique pure, sans courtier ni appel à Claude.

Les chiffres viennent des mêmes pièces que le desk (structure, risque,
registre) : le Risk Manager juge exactement ce que le desk s'apprête à faire.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, List, Optional, Sequence

import pandas as pd

from src.options import risque as rq


def vol_realisee(clotures: Sequence[float], jours: int) -> Optional[float]:
    """Volatilité réalisée annualisée sur les `jours` dernières séances, en %."""
    c = [x for x in clotures if x and x > 0]
    if len(c) < jours + 1:
        return None
    r = [math.log(c[i] / c[i - 1]) for i in range(len(c) - jours, len(c))]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252) * 100


def structure_par_terme(chaine: pd.DataFrame, spot: float) -> List[dict]:
    """Volatilité implicite à la monnaie (moyenne put/call), échéance par échéance."""
    sortie = []
    for e, g in chaine.groupby("echeance"):
        g = g.dropna(subset=["vol_implicite"])
        if g.empty:
            continue
        k = min(g["strike"].unique(), key=lambda x: abs(x - spot))
        atm = g[g["strike"] == k]
        cotees = atm.dropna(subset=["bid", "ask"])
        ecart = None
        if not cotees.empty and (cotees["vega"] > 0).all():
            ecart = round(float(((cotees["ask"] - cotees["bid"]) / cotees["vega"]).median()), 3)
        sortie.append({"echeance": e, "jours": int(g["dte"].iloc[0]), "strike_atm": float(k),
                       "vol_implicite_atm_pct": round(float(atm["vol_implicite"].mean()) * 100, 2),
                       "ecart_achat_vente_en_points_de_vol": ecart})
    return sorted(sortie, key=lambda x: x["jours"])


def construire(ouvrir, livre, chaine: pd.DataFrame, spot: float, vl: float,
               aujourd_hui: date, clotures: Sequence[float] = ()) -> dict:
    """L'instantané complet : proposition, livre, marché."""
    b = ouvrir.butterfly
    plus_haut = max(livre.plus_haut, vl)
    apres: rq.Livre = ouvrir.livre_apres
    stress_charte = apres.stress(spot, aujourd_hui) if apres else None
    vr21, vr63 = vol_realisee(clotures, 21), vol_realisee(clotures, 63)
    return {
        "proposition": {
            "echeance": b.echeance, "jours": b.dte, "lots": ouvrir.lots,
            "achat_put": b.aile_put, "vente_put_et_call": b.centre, "achat_call": b.aile_call,
            "credit_milieu": round(b.credit_milieu, 2), "credit_prix_affiche": round(b.credit_naturel, 2),
            "perte_max_par_lot_usd": round(b.perte_max_lot, 0),
            "vega_par_lot_usd_par_point": round(b.vega_lot, 1),
            "delta_par_lot_unites": round(b.delta_lot, 1),
            "vol_implicite_atm_pct": round(b.iv_atm * 100, 2),
            "mouvement_attendu_points": round(b.mouvement, 1),
            "mouvement_attendu_pct": round(b.mouvement / spot * 100, 2),
            "ailes_en_mouvements_attendus": 2.5,
            "point_mort_bas": round(b.centre - b.credit_naturel, 2),
            "point_mort_haut": round(b.centre + b.credit_naturel, 2),
        },
        "livre": {
            "valeur_liquidative": round(vl, 0), "plus_haut": round(plus_haut, 0),
            "baisse_depuis_plus_haut_pct": round((vl / plus_haut - 1) * 100, 2),
            "etat_charte": rq.etat_baisse(vl, plus_haut),
            "barreaux_ouverts": [{"echeance": x.echeance, "jours": x.dte(aujourd_hui),
                                  "strikes": [x.aile_put, x.centre, x.aile_call],
                                  "lots": x.lots, "credit": x.credit} for x in livre.barreaux],
            "mes": livre.mes,
            "vega_total_apres_usd_par_point": round(ouvrir.vega_total_apres, 0),
            "vega_max_charte_usd_par_point": round(0.0011 * vl, 0),
            "stress_charte_apres_usd": round(stress_charte, 0) if stress_charte is not None else None,
            "stress_charte_apres_pct_vl": round(stress_charte / vl * 100, 2) if stress_charte else None,
            "perte_max_totale_apres_usd": round(
                sum(x.perte_max_lot * x.lots for x in livre.barreaux) + b.perte_max_lot * ouvrir.lots, 0),
        },
        "marche": {
            "xsp": round(spot, 2),
            "vol_realisee_21j_pct": round(vr21, 2) if vr21 else None,
            "vol_realisee_63j_pct": round(vr63, 2) if vr63 else None,
            "prime_vs_realisee_21j_points": round(b.iv_atm * 100 - vr21, 2) if vr21 else None,
            "structure_par_terme": structure_par_terme(chaine, spot),
            "note": "Prix différés de 15 minutes (pas d'abonnement OPRA).",
        },
    }


def fonction_de_stress(ouvrir, spot: float, aujourd_hui: date):
    """Le scénario de stress que le Risk Manager peut rejouer à volonté."""
    apres: rq.Livre = ouvrir.livre_apres
    return lambda choc, dvol: apres.stress(spot, aujourd_hui, choc, dvol) if apres else 0.0
