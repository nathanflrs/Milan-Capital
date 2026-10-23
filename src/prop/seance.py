# src/prop/seance.py
"""
Les passages du prop trader (docs/desk/pods.md, section 1).

    python -m src.prop ouverture     # 9 h 45 New York : lire, proposer, revoir
    python -m src.prop suivi         # 12 h 30 : revoir, ouvrir si une place le mérite
    python -m src.prop cloture       # 16 h 10 : tenue des comptes, sans Claude

Un passage, de bout en bout :
    1. lire le compte ; rapprocher le registre avec le courtier — les stops et
       objectifs exécutés depuis le dernier passage sont fermés au prix réel ;
       un écart inexpliqué arrête le pod ;
    2. résultat du pod dans la séance → pause à −2 % ; limites du fonds ;
    3. (ouverture, suivi) le Prop Trader rend son plan ;
    4. ajustements des positions : sorties, stops, objectifs ;
    5. ouvertures : budget du code, puis relecture du Risk Manager, puis
       entrée et protection chez IBKR ;
    6. sauver le registre (en réel), noter le passage, publier.

La clôture ne fait que les étapes 1, 2 et 6 : c'est elle qui enregistre les
stops touchés dans l'après-midi et le résultat du jour du pod.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.equipe import socle as sc
from src.prop import livre as lv
from src.prop import ordres as od
from src.prop import regles as rg

DOSSIER = Path("logs/prop")
CLIENT_ID = int(os.getenv("PROP_CLIENT_ID", "23"))
ROLE = "Prop Trader"
MOMENTS = ("ouverture", "suivi", "cloture")


def _publier(texte: str, moment: str, mode: str, gravite: str = "info", role: str = ROLE) -> None:
    print(f"[{role}] {texte}")
    if gravite == "critical":
        sc.notifier_telephone(f"Prop — {role}", texte[:180], url="/", tag="prop-incident")
    try:
        from src.events.bus import Event, get_bus
        get_bus().emit(Event(type="desk", severity=gravite, title=role, body=texte,
                             meta={"role": role, "moment": moment, "mode": mode, "pod": "prop"}))
    except Exception as e:                       # le bus ne doit jamais arrêter le pod
        print(f"(bus d'événements indisponible : {e})", file=sys.stderr)


def plus_haut_du_fonds(vl: float, seances: Path = Path("logs/desk/seances.csv"),
                       journees: Path = DOSSIER / "journees.csv") -> float:
    """Le plus haut de la valeur liquidative du compte, relevé par le desk et par le pod."""
    haut = vl
    for chemin, col in ((seances, "valeur_liquidative"), (journees, "valeur_liquidative")):
        if chemin.exists():
            with chemin.open() as f:
                for l in csv.DictReader(f):
                    try:
                        haut = max(haut, float(l[col]))
                    except (KeyError, ValueError):
                        pass
    return haut


def clotures_veille(ohlcv: Dict, jour: date) -> Dict[str, float]:
    """La dernière clôture collectée avant `jour`, par titre."""
    import pandas as pd
    sortie = {}
    for t, df in ohlcv.items():
        avant = df.loc[:pd.Timestamp(jour) - pd.Timedelta(days=1)]
        if len(avant):
            sortie[t] = float(avant["Close"].iloc[-1])
    return sortie


def noter_journee(jour: date, vl: float, livre: lv.Livre, resultat_jour: float, mode: str,
                  chemin: Path = DOSSIER / "journees.csv") -> None:
    """Le relevé de fin de séance du pod, écrit par le code : base de sa mesure."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not chemin.exists()
    fermes = [t for t in livre.trades if t.ferme_le == jour.isoformat()]
    with chemin.open("a", newline="") as f:
        w = csv.writer(f)
        if nouveau:
            w.writerow(["jour", "mode", "valeur_liquidative", "resultat_du_jour", "positions",
                        "trades_fermes_du_jour", "resultat_realise_cumule", "r_cumule"])
        w.writerow([jour.isoformat(), mode, round(vl, 2), round(resultat_jour, 2),
                    len(livre.positions), len(fermes),
                    round(sum(t.resultat_usd for t in livre.trades), 2),
                    round(sum(t.r for t in livre.trades), 2)])


def _noter_passage(jour: date, moment: str, mode: str, vl: float, resume: dict,
                   chemin: Path = DOSSIER / "seances.csv") -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not chemin.exists()
    with chemin.open("a", newline="") as f:
        w = csv.writer(f)
        if nouveau:
            w.writerow(["jour", "moment", "mode", "valeur_liquidative", "proposes", "acceptes_code",
                        "approuves_rm", "ouverts", "ajustements", "cout_usd"])
        w.writerow([jour.isoformat(), moment, mode, round(vl, 2), resume.get("proposes", 0),
                    resume.get("acceptes", 0), resume.get("approuves", 0), resume.get("ouverts", 0),
                    resume.get("ajustements", 0), round(resume.get("cout", 0.0), 4)])


def _jour_new_york() -> date:
    return datetime.now(sc.NEW_YORK).date()


def _valeur_liquidative(ib) -> float:
    for v in ib.accountSummary():
        if v.tag == "NetLiquidation":
            return float(v.value)
    raise RuntimeError("valeur liquidative introuvable")


def passage(moment: str, jour: Optional[date] = None, livre_chemin: Path = lv.LIVRE) -> int:
    from ib_insync import IB

    from src.market.view import load_market_view
    from src.prop import calendrier as cal
    from src.prop import indicateurs as ind
    from src.prop import trader as tr

    logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
    jour = jour or _jour_new_york()
    mode = od.mode_autorise()
    dire = lambda texte, g="info", role=ROLE: _publier(texte, moment, mode, g, role)
    resume = {"cout": 0.0}

    ib = IB()
    ib.RequestTimeout = 120
    ib.connect(os.getenv("IBKR_HOST", "127.0.0.1"), int(os.getenv("IBKR_PORT", "4002")),
               clientId=CLIENT_ID)
    try:
        vl = _valeur_liquidative(ib)
        livre = lv.charger(livre_chemin)
        sauver = (lambda: lv.sauver(livre, livre_chemin)) if mode == od.MODE_REEL else (lambda: None)

        # 1. Rapprochement : ce que les stops et objectifs ont fermé, puis concordance.
        rap = lv.rapprocher(livre, ib.positions(), ib.reqExecutions(), jour)
        for t in rap.fermes:
            dire(f"{t.ticker} : {t.motif} exécuté à {t.sortie:g}, {t.resultat_usd:+,.0f} $ "
                 f"({t.r:+.2f} R).", "warning" if t.resultat_usd < 0 else "info")
            sc.notifier_telephone(ROLE, f"{t.ticker} : {t.motif} touché, {t.resultat_usd:+,.0f} $ "
                                        f"({t.r:+.2f} R).", url="/?membre=prop-trader",
                                  tag=f"prop-{t.id}")
        if not rap.ok:
            sauver()
            dire(f"Écart avec le courtier : {rap.resume()}. Le pod ne décide rien tant qu'un "
                 f"humain n'a pas compris.", "critical", "Middle Office")
            return 1

        # 2. Le marché d'hier, le résultat du jour, les limites.
        vue = load_market_view()
        membres = list(vue.members.index)
        veille = clotures_veille(vue.ohlcv, jour)
        cours_pos = od.cours(ib, [p.ticker for p in livre.positions])
        resultat_jour, sans_cours = lv.resultat_du_jour(livre, jour, cours_pos, veille)
        if sans_cours:
            dire(f"Sans cours : {', '.join(sans_cours)} (comptés à zéro dans le résultat du jour).",
                 "warning")
        plus_haut = plus_haut_du_fonds(vl)
        if resultat_jour <= -rg.PAUSE_JOUR * vl and not livre.en_pause(jour):
            livre.pause_le = jour.isoformat()
            dire(f"Pause du pod : {resultat_jour:+,.0f} $ dans la séance. Plus d'ouverture "
                 f"jusqu'à demain.", "critical")
        permises, motif = rg.peut_ouvrir(livre, jour, vl, plus_haut, resultat_jour)

        if moment == "cloture":
            sauver()
            noter_journee(jour, vl, livre, resultat_jour, mode)
            dire(f"Clôture : {len(livre.positions)} position(s), résultat du jour "
                 f"{resultat_jour:+,.0f} $, {len(rap.fermes)} sortie(s) chez le courtier.")
            return 0

        # 3. Le plan du Prop Trader.
        agenda = cal.agenda(jour, membres)
        table = ind.ecran(vue.ohlcv, vue.members)
        ctx = tr.Contexte(jour=jour, moment=moment, table=table, ohlcv=vue.ohlcv,
                          membres=vue.members, agenda=agenda, livre=livre, vl=vl,
                          plus_haut=plus_haut, perte_du_jour=resultat_jour,
                          ouvertures=(permises, motif), cours=lambda ts: od.cours(ib, ts),
                          as_of=vue.as_of.isoformat())
        r = tr.proposer(ctx)
        resume["cout"] += r.cout
        sc.publier(tr.MEMBRE, moment, r, notifier=False)
        if not r.ok:
            sauver()
            _noter_passage(jour, moment, mode, vl, resume)
            return 1
        plan = r.memo
        lignes: List[str] = []

        # 4. Ajustements : ils réduisent le risque ou le bornent, sans relecture.
        for a in plan.ajustements:
            p = livre.position(a.id_position)
            if p is None or a.action == "garder":
                continue
            refus = rg.valider_ajustement(p, a.action, a.nouveau_prix, cours_pos.get(p.ticker), vl)
            if refus:
                dire(f"{p.ticker} : {a.action} refusé par le code — {refus}.", "warning")
                continue
            resume["ajustements"] = resume.get("ajustements", 0) + 1
            if mode != od.MODE_REEL:
                dire(f"(simulation) {p.ticker} : {a.action}"
                     f"{f' à {a.nouveau_prix:g}' if a.nouveau_prix else ''} — {a.raison[:140]}")
                continue
            if a.action == "sortir":
                (c,) = od.contrats(ib, [p.ticker]).values()
                s = od.sortir(ib, c, p.id, p.sens, p.quantite, cours_pos[p.ticker])
                if s.rempli:
                    t = livre.fermer(p, s.prix_moyen, jour.isoformat(), "sortie", s.commission or 0.0,
                                     quantite=s.rempli)
                    lignes.append(f"{t.ticker} sorti {t.resultat_usd:+,.0f} $ ({t.r:+.2f} R)")
                    dire(f"{t.ticker} sorti à {t.sortie:g} : {t.resultat_usd:+,.0f} $ ({t.r:+.2f} R). "
                         f"{a.raison[:140]}")
                if p in livre.positions:          # pas (ou pas tout) sorti : reprotéger
                    od.proteger(ib, c, p.id, p.sens, p.quantite, p.stop, p.objectif)
                    dire(f"{p.ticker} : sortie {s.statut}, {p.quantite} titres reprotégés.", "warning")
            else:
                quoi = "stop" if a.action == "deplacer_stop" else "objectif"
                if od.deplacer(ib, p.id, quoi, a.nouveau_prix):
                    setattr(p, quoi, round(a.nouveau_prix, 2))
                    dire(f"{p.ticker} : {quoi} déplacé à {a.nouveau_prix:g}. {a.raison[:140]}")
                else:
                    dire(f"{p.ticker} : {quoi} introuvable chez IBKR, non déplacé.", "critical")

        # 5. Ouvertures : budget du code, relecture, exécution.
        demandes = tr.demandes(plan)
        resume["proposes"] = len(demandes)
        if demandes and not permises:
            dire(f"{len(demandes)} trade(s) proposé(s), aucun ouvert : {motif}", "warning")
        elif demandes:
            cours_dem = od.cours(ib, [d.ticker for d in demandes if d.ticker in vue.ohlcv])
            acceptes, refus = rg.valider(demandes, livre, vl, plus_haut, membres, cours_dem)
            resume["acceptes"] = len(acceptes)
            for t, m in refus:
                dire(f"{t} refusé par le code : {m}.", "warning")
            if acceptes:
                verdicts = _relecture(acceptes, livre, table, vue.members, agenda, cours_dem,
                                      vl, jour)
                for o in acceptes:
                    ok, pourquoi = verdicts.get(o.ticker, (False, "pas de verdict"))
                    if not ok:
                        dire(f"{o.ticker} freiné : {pourquoi}", "warning", "Risk Manager")
                        continue
                    resume["approuves"] = resume.get("approuves", 0) + 1
                    ligne = _ouvrir(ib, o, livre, jour, mode, dire)
                    if ligne:
                        resume["ouverts"] = resume.get("ouverts", 0) + 1
                        lignes.append(ligne)

        sauver()
        _noter_passage(jour, moment, mode, vl, resume)
        bilan = (f"{moment.capitalize()} : {resume.get('proposes', 0)} proposé(s), "
                 f"{resume.get('ouverts', 0)} ouvert(s)" + (f" — {'; '.join(lignes)}" if lignes else "")
                 + f". {len(livre.positions)} position(s).")
        dire(bilan)
        sc.notifier_telephone(ROLE, f"{plan.recap_court[:110]} {bilan}"[:240],
                              url="/?membre=prop-trader", tag=f"prop-{moment}")
        return 0
    except Exception as e:
        dire(f"Passage interrompu : {e}", "critical", "Middle Office")
        raise
    finally:
        ib.disconnect()


def _relecture(acceptes, livre, table, membres, agenda, cours, vl, jour) -> dict:
    """{ticker: (autorisé ?, motif)} — toute défaillance freine tout le lot."""
    try:
        from src.equipe import risk_manager
        secteurs = membres["sector"].to_dict()
        lot = [{"ticker": o.ticker, "sens": "achat" if o.demande.sens > 0 else "vente_a_decouvert",
                "quantite": o.quantite, "entree": o.limite, "stop": o.demande.stop,
                "objectif": o.demande.objectif, "montant_usd": o.montant_usd,
                "montant_pct_vl": round(o.montant_usd / vl * 100, 2), "risque_usd": o.risque_usd,
                "gain_au_objectif_usd": round(o.quantite * abs(o.demande.objectif - o.limite), 0),
                "cours_actuel": cours.get(o.ticker), "horizon": o.demande.horizon,
                "catalyseur": o.demande.catalyseur, "these": o.demande.these,
                "indicateurs": json.loads(table.loc[o.ticker].to_json()) if o.ticker in table.index else None}
               for o in acceptes]
        contexte = {"lot": lot, "agenda": agenda, "livre": {
            "positions": [{"ticker": p.ticker, "sens": p.sens, "quantite": p.quantite,
                           "entree": p.entree, "stop": p.stop, "secteur": secteurs.get(p.ticker)}
                          for p in livre.positions],
            "exposition_apres_le_lot": rg.exposition(livre.positions, acceptes, cours, secteurs, vl),
            "valeur_liquidative": round(vl)}}
        verdicts, message, _ = risk_manager.relire_prop(contexte, jour)
        print(f"[Risk Manager] {message}")
        return verdicts
    except Exception as e:
        print(f"[Risk Manager] relecture impossible ({type(e).__name__} : {e}) : aucune ouverture.")
        return {}


def _ouvrir(ib, o: rg.Ordre, livre: lv.Livre, jour: date, mode: str, dire) -> Optional[str]:
    d = o.demande
    id_ = livre.nouvel_id(jour, o.ticker)
    cs = od.contrats(ib, [o.ticker])
    if o.ticker not in cs:
        dire(f"{o.ticker} introuvable chez IBKR.", "warning")
        return None
    c = cs[o.ticker]
    sens_txt = "achat" if d.sens > 0 else "vente à découvert"
    r = od.entrer(ib, c, id_, d.sens, o.quantite, o.limite, mode)
    if mode != od.MODE_REEL:
        dire(f"(simulation) {o.ticker} {sens_txt} {o.quantite} à {o.limite:g}, stop {d.stop:g}, "
             f"objectif {d.objectif:g} : {r.statut}"
             f"{f', marge {r.marge_initiale:,.0f} $' if r.marge_initiale else ''}"
             f"{f' — {r.detail[:120]}' if r.detail else ''}.")
        return None
    if not r.rempli:
        dire(f"{o.ticker} {sens_txt} à {o.limite:g} : non exécuté ({r.statut}).")
        return None
    od.proteger(ib, c, id_, d.sens, r.rempli, d.stop, d.objectif)
    livre.ouvrir(lv.Position(id_, o.ticker, d.sens, r.rempli, r.prix_moyen, round(d.stop, 2),
                             round(d.objectif, 2), jour.isoformat(),
                             round(r.rempli * abs(r.prix_moyen - d.stop), 2), d.these[:600],
                             d.catalyseur[:200], d.horizon, r.commission or 0.0))
    dire(f"{o.ticker} : {sens_txt} {r.rempli} à {r.prix_moyen:g}, stop {d.stop:g}, objectif "
         f"{d.objectif:g} (risque {r.rempli * abs(r.prix_moyen - d.stop):,.0f} $).")
    return f"{o.ticker} {'↑' if d.sens > 0 else '↓'} {r.rempli}"


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Un passage du prop trader.")
    p.add_argument("moment", choices=MOMENTS)
    return passage(p.parse_args(argv).moment)


if __name__ == "__main__":
    sys.exit(main())
