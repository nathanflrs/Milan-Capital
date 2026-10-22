#!/usr/bin/env python
"""
Desk de volatilité — phase 1-ter : la conviction peut-elle se mesurer ?

    python -m scripts.desk_phase1ter_conviction

Protocole : docs/desk/phase1ter_conviction.md, écrit avec Nathan et commité
(836bb67) AVANT ce script. Rien n'est réglé ici qui n'y soit écrit.

Mécanique de la phase 1-bis inchangée (importée), plus une taille variable :
    S(t) = VIX(t) − agitation des 21 séances jusqu'à t
    tiers de S calculés sur les seules séances antérieures → ×0,5 / ×1 / ×2
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.desk_phase1_indices_cboe import ROOT, _ols_newey_west, charger
from scripts.desk_phase1bis_vente_variance import (
    CHARTE_PERTE_MAX, DEBUT, DUREE, EPISODES, FIN, GRILLE_N, PERIODES_PAR_AN,
    mesures, periodes, pire_baisse)

OUT = ROOT / "logs" / "desk_phase1ter_results.json"

DEPART_REFERENCE = 13          # départ médian de la phase 1-bis, fixé d'avance
PALIERS = (0.5, 1.0, 2.0)
RODAGE = 252                   # séances d'historique avant d'utiliser les tiers
COUPURE = "2008-01-01"         # K3 : 1990-2007 contre 2008-2026
K2_DEPARTS_MIN = 15


def signaux(jours: pd.DataFrame) -> dict[str, pd.Series]:
    rv_passee = np.sqrt(PERIODES_PAR_AN * jours["r"].pow(2).rolling(DUREE).sum()) * 100
    return {
        "prime": jours["VIX"] - rv_passee,              # le signal du verdict
        "niveau_vix": jours["VIX"],                     # rapportés à côté
        "rapport_vix_agitation": jours["VIX"] / rv_passee,
    }


def multiplicateurs(s: pd.Series) -> pd.Series:
    """Palier de chaque séance, à partir des seules valeurs de S antérieures."""
    s = s.dropna()
    bas = s.expanding(min_periods=RODAGE).quantile(1 / 3).shift(1)
    haut = s.expanding(min_periods=RODAGE).quantile(2 / 3).shift(1)
    m = pd.Series(PALIERS[1], index=s.index)
    m[s < bas] = PALIERS[0]
    m[s >= haut] = PALIERS[2]
    return m          # avant le rodage, bas/haut valent NaN → ×1


def avec_conviction(p: pd.DataFrame, s: pd.Series, m: pd.Series) -> pd.DataFrame:
    p = p.copy()
    p["signal"] = s.reindex(p["entree"]).to_numpy()
    p["mult"] = m.reindex(p["entree"]).fillna(PALIERS[1]).to_numpy()
    p["gain_pts_conv"] = p["mult"] * p["gain_pts"]
    return p


def taille(departs: dict, col: str) -> float:
    n_max = 0.0
    for n in GRILLE_N:
        if all(pire_baisse(p, n, col) >= CHARTE_PERTE_MAX for p in departs.values()):
            n_max = float(n)
    return n_max


def pente(p: pd.DataFrame) -> dict:
    q = p.dropna(subset=["signal"])
    b, se = _ols_newey_west(q["gain_pts"].to_numpy(), q["signal"].to_numpy())
    return {"pente": float(b[1]),
            "ic95": [float(b[1] - 1.96 * se[1]), float(b[1] + 1.96 * se[1])],
            "periodes": int(len(q))}


def exces(p: pd.DataFrame, n: float, col: str) -> float:
    return float((n / 100 * p[col]).mean() * PERIODES_PAR_AN)


def comparer(departs: dict, n_fixe: float, n_conv: float) -> dict:
    """Gain annuel au-dessus du cash, taille fixe contre conviction, par départ."""
    return {d: {"fixe": exces(p, n_fixe, "gain_pts"),
                "conviction": exces(p, n_conv, "gain_pts_conv")}
            for d, p in departs.items()}


def episodes(p: pd.DataFrame, n_fixe: float, n_conv: float) -> dict:
    out = {}
    for nom, (a, b) in EPISODES.items():
        t = p[(p["entree"] <= b) & (p.index >= pd.Timestamp(a))]
        out[nom] = {
            "paliers": [float(x) for x in t["mult"]],
            "fixe": float((1 + n_fixe / 100 * t["gain_pts"]).prod() - 1),
            "conviction": float((1 + n_conv / 100 * t["gain_pts_conv"]).prod() - 1)}
    return out


def evaluer(jours: pd.DataFrame, base: dict, s: pd.Series, n_fixe: float) -> dict:
    m = multiplicateurs(s)
    departs = {d: avec_conviction(p, s, m) for d, p in base.items()}
    n_conv = taille(departs, "gain_pts_conv")
    ref = departs[DEPART_REFERENCE]
    comp = comparer(departs, n_fixe, n_conv)
    gagnants = sum(c["conviction"] > c["fixe"] for c in comp.values())

    moities = {}
    for nom, masque in (("1990-2007", ref["entree"] < COUPURE),
                        ("2008-2026", ref["entree"] >= COUPURE)):
        q = ref[masque]
        moities[nom] = {"pente": pente(q),
                        "fixe": exces(q, n_fixe, "gain_pts"),
                        "conviction": exces(q, n_conv, "gain_pts_conv")}

    k1 = pente(ref)
    criteres = {
        "K1": k1["ic95"][0] > 0,
        "K2": comp[DEPART_REFERENCE]["conviction"] > comp[DEPART_REFERENCE]["fixe"]
              and gagnants >= K2_DEPARTS_MIN,
        "K3": all(v["pente"]["pente"] > 0 and v["conviction"] > v["fixe"]
                  for v in moities.values()),
    }
    mf, mc = mesures(ref, n_fixe), mesures(ref, n_conv, "gain_pts_conv")
    return {
        "n_conviction": n_conv, "k1": k1, "comparaison_depart_ref": comp[DEPART_REFERENCE],
        "departs_ou_conviction_gagne": gagnants, "moities": moities,
        "criteres": criteres,
        "repartition_paliers": {str(k): float(v) for k, v in
                                ref["mult"].value_counts(normalize=True).sort_index().items()},
        "fixe": {k: mf[k] for k in ("sharpe", "exces_annuel", "volatilite", "baisse_max",
                                    "baisse_creux", "pire_periode", "pire_periode_sortie")},
        "conviction": {k: mc[k] for k in ("sharpe", "exces_annuel", "volatilite", "baisse_max",
                                          "baisse_creux", "pire_periode", "pire_periode_sortie")},
        "episodes": episodes(ref, n_fixe, n_conv),
    }


def main() -> None:
    niveaux, rf = charger()
    jours = niveaux[["SPTR", "VIX"]].loc[DEBUT:FIN].dropna()
    jours["r"] = np.log(jours["SPTR"]).diff()
    jours["RF"] = rf.reindex(jours.index).ffill()
    jours = jours.dropna()
    base = {d: periodes(jours, d) for d in range(DUREE)}
    n_fixe = taille(base, "gain_pts")
    print(f"Taille fixe (référence 1-bis) : N = {n_fixe:.2f}\n")

    res = {"n_fixe": n_fixe, "signaux": {}}
    for nom, s in signaux(jours).items():
        r = evaluer(jours, base, s, n_fixe)
        res["signaux"][nom] = r
        titre = "VERDICT" if nom == "prime" else "à côté, sans effet sur le verdict"
        print(f"══ {nom} ({titre})")
        print(f"N conviction = {r['n_conviction']:.2f} ; paliers {r['repartition_paliers']}")
        print(f"K1 pente {r['k1']['pente']:.3f} IC95 {np.round(r['k1']['ic95'], 3)}")
        print(f"Départ 13 : {r['comparaison_depart_ref']} ; "
              f"départs où la conviction gagne : {r['departs_ou_conviction_gagne']}/21")
        for m, v in r["moities"].items():
            print(f"  {m} : pente {v['pente']['pente']:.3f} IC95 "
                  f"{np.round(v['pente']['ic95'], 3)} ; fixe {v['fixe']:.4f} ; "
                  f"conviction {v['conviction']:.4f}")
        print("  " + pd.DataFrame({"fixe": r["fixe"], "conviction": r["conviction"]}).T
              .to_string(float_format=lambda x: f"{x:.4f}").replace("\n", "\n  "))
        for e, v in r["episodes"].items():
            print(f"  {e:18s} paliers {v['paliers']}  fixe {v['fixe']:+.2%}  "
                  f"conviction {v['conviction']:+.2%}")
        print(f"  CRITÈRES {r['criteres']}\n")

    # HORS PROTOCOLE — ajouté après la mesure : quel départ fixe la taille ?
    s = signaux(jours)["prime"]
    m = multiplicateurs(s)
    n_conv = res["signaux"]["prime"]["n_conviction"]
    diag = {}
    for d, p in base.items():
        q = avec_conviction(p, s, m)
        g = n_conv / 100 * q["gain_pts_conv"]
        diag[d] = {"baisse_max": pire_baisse(q, n_conv, "gain_pts_conv"),
                   "pire_periode": float(g.min()),
                   "pire_periode_sortie": str(g.idxmin().date()),
                   "palier": float(q.loc[g.idxmin(), "mult"]),
                   "vix_entree": float(q.loc[g.idxmin(), "vix"]),
                   "rv": float(q.loc[g.idxmin(), "rv"])}
    pire = min(diag, key=lambda d: diag[d]["baisse_max"])
    res["hors_protocole_depart_limitant"] = {"depart": pire, **diag[pire],
                                             "par_depart": diag}
    print(f"HORS PROTOCOLE — départ qui fixe la taille : {pire} {diag[pire]}")

    res["verdict"] = res["signaux"]["prime"]["criteres"]
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"Écrit : {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
