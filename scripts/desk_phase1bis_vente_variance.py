#!/usr/bin/env python
"""
Desk de volatilité — phase 1-bis : vendre la volatilité sans subir le marché.

    python -m scripts.desk_phase1bis_vente_variance

Protocole : docs/desk/phase1bis_vente_variance.md, écrit avec Nathan et commité
(108dff9) AVANT ce script. Rien n'est réglé ici qui n'y soit écrit.

Swap de variance à 21 séances, rejoué sur le VIX depuis 1990 :
    K   = VIX(t) − 1                                   (1 point de frais)
    RV  = √(252/21 × Σ r²) sur les 21 séances suivantes
    RVp = min(RV, 2,5 × VIX(t))                        (plafond)
    gain en points de vol = (K² − RVp²) / (2K)
    gain en % du capital  = N × gain en points
Données : celles de la phase 1 (logs/desk_cache/), chargées par le même code.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.desk_phase1_indices_cboe import ROOT, _ols_newey_west, baisse_max, charger

OUT = ROOT / "logs" / "desk_phase1bis_results.json"

DUREE = 21                     # séances par période (≈ 30 jours calendaires)
PERIODES_PAR_AN = 252 / DUREE
FRAIS_POINTS = 1.0
PLAFOND = 2.5
DEBUT, FIN = "1990-01-01", None
RECENT = "2015-01-01"
CHARTE_PERTE_MAX = -0.15
GRILLE_N = np.round(np.arange(0.01, 3.001, 0.01), 2)   # % du capital par point de vol

EPISODES = {
    "LTCM 1998": ("1998-08-01", "1998-10-31"),
    "2008": ("2008-09-01", "2008-11-30"),
    "août 2011": ("2011-08-01", "2011-08-31"),
    "Volmageddon 2018": ("2018-02-01", "2018-02-28"),
    "mars 2020": ("2020-03-01", "2020-03-31"),
    "avril 2025": ("2025-04-01", "2025-04-30"),
}


def periodes(jours: pd.DataFrame, depart: int) -> pd.DataFrame:
    """Une ligne par période non chevauchante commençant à la séance `depart`."""
    r2 = jours["r"].pow(2).to_numpy()
    vix = jours["VIX"].to_numpy()
    sp = jours["SPTR"].to_numpy()
    rf = jours["RF"].to_numpy()
    lignes = []
    for i in range(depart, len(jours) - DUREE, DUREE):
        k = vix[i] - FRAIS_POINTS
        rv = np.sqrt(PERIODES_PAR_AN * r2[i + 1:i + DUREE + 1].sum()) * 100
        rv_p = min(rv, PLAFOND * vix[i])
        rf_p = rf[i + 1:i + DUREE + 1].mean() / 100 / PERIODES_PAR_AN
        lignes.append({
            "entree": jours.index[i], "sortie": jours.index[i + DUREE],
            "vix": vix[i], "rv": rv,
            "gain_pts": (k * k - rv_p * rv_p) / (2 * k),
            "gain_pts_sans_plafond": (k * k - rv * rv) / (2 * k),
            "rf": rf_p,
            "marche_exces": sp[i + DUREE] / sp[i] - 1 - rf_p,
        })
    return pd.DataFrame(lignes).set_index("sortie")


def en_capital(p: pd.DataFrame, n: float, col: str = "gain_pts") -> pd.Series:
    """Rendement de la période pour le fonds : taux sans risque + N % par point."""
    return p["rf"] + n / 100 * p[col]


def pire_baisse(p: pd.DataFrame, n: float, col: str = "gain_pts") -> float:
    # clip : une période qui perd plus que le capital ruine le fonds (−100 %)
    niveau = (1 + en_capital(p, n, col)).clip(lower=0).cumprod()
    return baisse_max(niveau)[0]


def mesures(p: pd.DataFrame, n: float, col: str = "gain_pts") -> dict:
    exc = n / 100 * p[col]
    mkt = p["marche_exces"]
    b, se = _ols_newey_west(exc.to_numpy(), mkt.to_numpy())
    rec = exc[p["entree"] >= RECENT]
    niveau = (1 + en_capital(p, n, col)).clip(lower=0).cumprod()
    dd, d0, creux, duree = baisse_max(niveau)
    return {
        "periodes": int(len(p)),
        "sharpe": float(exc.mean() / exc.std() * np.sqrt(PERIODES_PAR_AN)),
        "sharpe_marche": float(mkt.mean() / mkt.std() * np.sqrt(PERIODES_PAR_AN)),
        "exces_annuel": float(exc.mean() * PERIODES_PAR_AN),
        "volatilite": float(exc.std() * np.sqrt(PERIODES_PAR_AN)),
        "alpha_annuel": float(b[0] * PERIODES_PAR_AN),
        "alpha_ic95": [float((b[0] - 1.96 * se[0]) * PERIODES_PAR_AN),
                       float((b[0] + 1.96 * se[0]) * PERIODES_PAR_AN)],
        "beta": float(b[1]),
        "correlation": float(np.corrcoef(exc, mkt)[0, 1]),
        "exces_annuel_depuis_2015": float(rec.mean() * PERIODES_PAR_AN),
        "baisse_max": dd, "baisse_debut": d0, "baisse_creux": creux,
        "jours_pour_revenir": duree,
        "pire_periode": float(exc.min()),
        "pire_periode_sortie": str(exc.idxmin().date()),
        "part_periodes_gagnantes": float((exc > 0).mean()),
        "gain_pts_moyen": float(p[col].mean()),
        "gain_pts_median": float(p[col].median()),
    }


def criteres(m: dict) -> dict:
    return {"C1": m["sharpe"] >= m["sharpe_marche"],
            "C2": m["alpha_ic95"][0] > 0,
            "C3": m["beta"] < 0.3,
            "C4": m["exces_annuel_depuis_2015"] > 0}


def episodes(p: pd.DataFrame, n: float) -> dict:
    out = {}
    for nom, (a, b) in EPISODES.items():
        touche = p[(p["entree"] <= b) & (p.index >= pd.Timestamp(a))]
        cap = en_capital(touche, n) - touche["rf"]
        out[nom] = {"periodes": [f"{e.date()} → {s.date()}" for e, s in
                                 zip(touche["entree"], touche.index)],
                    "vix_entree": [round(float(v), 1) for v in touche["vix"]],
                    "rv": [round(float(v), 1) for v in touche["rv"]],
                    "resultat": float((1 + cap).prod() - 1)}
    return out


def main() -> None:
    niveaux, rf = charger()
    jours = niveaux[["SPTR", "VIX"]].loc[DEBUT:FIN].dropna()
    jours["r"] = np.log(jours["SPTR"]).diff()
    jours["RF"] = rf.reindex(jours.index).ffill()
    jours = jours.dropna()
    print(f"Séances : {jours.index[0].date()} → {jours.index[-1].date()} ({len(jours)})")

    departs = {d: periodes(jours, d) for d in range(DUREE)}

    # Taille : plus grand N qui garde −15 % pour les 21 départs (version plafonnée)
    n_charte = 0.0
    for n in GRILLE_N:
        if all(pire_baisse(p, n) >= CHARTE_PERTE_MAX for p in departs.values()):
            n_charte = float(n)
    print(f"Taille charte : N = {n_charte:.2f} % du capital par point de volatilité\n")

    toutes = {d: mesures(p, n_charte) for d, p in departs.items()}
    ordre = sorted(toutes, key=lambda d: toutes[d]["sharpe"])
    median, pire = ordre[len(ordre) // 2], ordre[0]
    m = toutes[median]
    sans_plafond = mesures(departs[median], n_charte, "gain_pts_sans_plafond")
    verdict = criteres(m)
    parts = {c: float(np.mean([criteres(toutes[d])[c] for d in toutes]))
             for c in verdict}

    table = pd.DataFrame({"plafonné (médian)": m, "plafonné (pire départ)": toutes[pire],
                          "sans plafond (médian)": sans_plafond}).drop(
        ["alpha_ic95"])
    print(f"Départ médian : séance {median} ; pire départ : séance {pire}")
    print(table.to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"\nIC 95 % de l'alpha (médian) : {m['alpha_ic95']}")
    print(f"Critères (médian) : {verdict}")
    print(f"Part des 21 départs qui passent : {parts}\n")

    ep = episodes(departs[median], n_charte)
    for nom, e in ep.items():
        print(f"{nom:18s} {e['resultat']:+.2%}  VIX {e['vix_entree']}  RV {e['rv']}")

    # HORS PROTOCOLE — ajouté après la mesure : que coûterait plus de taille ?
    plus_gros = {}
    for n in (n_charte, 0.25, 0.50):
        pm = mesures(departs[median], n)
        plus_gros[f"N={n:.2f}"] = {
            "exces_annuel": pm["exces_annuel"], "volatilite": pm["volatilite"],
            "baisse_max": pm["baisse_max"], "pire_periode": pm["pire_periode"],
            "pire_baisse_21_departs": min(pire_baisse(p, n) for p in departs.values())}
    print("\nHORS PROTOCOLE — plus de taille :")
    print(pd.DataFrame(plus_gros).to_string(float_format=lambda x: f"{x:.3f}"))

    res = {"hors_protocole_plus_de_taille": plus_gros, "n_charte": n_charte, "depart_median": median, "pire_depart": pire,
           "median": m, "pire": toutes[pire], "sans_plafond_median": sans_plafond,
           "criteres": verdict, "part_departs_qui_passent": parts,
           "sharpe_par_depart": {d: toutes[d]["sharpe"] for d in toutes},
           "episodes": ep}
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\nÉcrit : {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
