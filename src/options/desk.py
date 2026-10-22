# src/options/desk.py
"""
Pièce 7b de la couche options : la séance du desk.

    python -m src.options.desk 10:30
    python -m src.options.desk 15:30

Un contrôle, de bout en bout :
    1. lire le compte (valeur liquidative, positions) et la chaîne XSP ;
    2. Middle Office : rapprocher le registre avec le courtier ;
    3. décider (decisions.py) : fermetures, ouverture du barreau de la semaine ;
    4. exécuter (execution.py), puis mettre le registre à jour sur ce qui a
       VRAIMENT été rempli — jamais sur ce qui a été demandé ;
    5. Execution Trader : couvrir l'exposition restante en MES ;
    6. sauver le registre, publier chaque action de l'équipe.

Le mode vient d'execution.mode_autorise() : **simulation** tant que
DESK_ENABLED et EXECUTION_ENABLED ne sont pas tous deux ouverts. En
simulation, les ordres sont soumis à IBKR en whatIf, rien n'est transmis, et
le registre ne bouge pas — on voit ce que le desk *aurait* fait.

Chaque action est publiée sur le bus d'événements (type « desk », rôle dans
meta) : c'est ce que la salle des marchés affichera.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from src.options import decisions as dc
from src.options import execution as ex
from src.options import registre as rg

DOSSIER = Path("logs/desk")
CLIENT_ID = int(os.getenv("DESK_CLIENT_ID", "22"))
ZONE_SEANCE = 0.35


def _publier(role: str, texte: str, moment: str, mode: str, gravite: str = "info") -> None:
    print(f"[{role}] {texte}")
    try:
        from src.events.bus import Event, get_bus
        get_bus().emit(Event(type="desk", severity=gravite, title=role, body=texte,
                             meta={"role": role, "moment": moment, "mode": mode}))
    except Exception as e:                       # le bus ne doit jamais arrêter le desk
        print(f"(bus d'événements indisponible : {e})", file=sys.stderr)


def _valeur_liquidative(ib) -> float:
    for v in ib.accountSummary():
        if v.tag == "NetLiquidation":
            return float(v.value)
    raise RuntimeError("valeur liquidative introuvable")


def _clotures_xsp(ib) -> list:
    """Clôtures quotidiennes de l'indice XSP sur ~4 mois, pour la volatilité réalisée."""
    try:
        from ib_insync import Index
        barres = ib.reqHistoricalData(Index("XSP", "CBOE", "USD"), endDateTime="",
                                      durationStr="4 M", barSizeSetting="1 day",
                                      whatToShow="TRADES", useRTH=True)
        return [b.close for b in barres]
    except Exception as e:
        print(f"(volatilité réalisée indisponible : {e})", file=sys.stderr)
        return []


def _relecture(ib, ouvrir, livre, chaine, spot: float, vl: float, aujourd_hui: date):
    """(autorisé ?, motif) — l'avis du Risk Manager, toute défaillance valant frein."""
    try:
        from src.equipe import contexte, risk_manager
        ctx = contexte.construire(ouvrir, livre, chaine, spot, vl, aujourd_hui, _clotures_xsp(ib))
        ok, motif, _ = risk_manager.relire(ctx, contexte.fonction_de_stress(ouvrir, spot, aujourd_hui),
                                           aujourd_hui)
        return ok, motif
    except Exception as e:
        return False, f"Relecture impossible ({type(e).__name__} : {e}) : pas d'ouverture."


def seance(moment: str, aujourd_hui: Optional[date] = None,
           livre_chemin: Path = rg.LIVRE) -> int:
    from ib_insync import IB

    from src.options.collect import choisir_echeances, collecter_symbole

    logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
    aujourd_hui = aujourd_hui or date.today()
    mode = ex.mode_autorise()
    dire = lambda role, texte, g="info": _publier(role, texte, moment, mode, g)
    dire(dc.MO, f"Séance de {moment}, mode {mode}.")

    ib = IB()
    ib.RequestTimeout = 120
    ib.connect(os.getenv("IBKR_HOST", "127.0.0.1"), int(os.getenv("IBKR_PORT", "4002")),
               clientId=CLIENT_ID)
    try:
        ib.reqMarketDataType(int(os.getenv("OPTIONS_MARKET_DATA_TYPE", "3")))
        vl = _valeur_liquidative(ib)
        livre = rg.charger(livre_chemin)
        if not livre.vl_armement:
            livre.vl_armement = vl
        rap = rg.rapprocher(livre, ib.positions())
        if rap.hors_desk:
            dire(dc.MO, f"Lignes hors desk dans le compte : {', '.join(rap.hors_desk)}.", "warning")

        # Photo propre à la séance : l'échéance cible (25-35 j) ET celles des
        # barreaux ouverts, même sous 7 jours — sinon un barreau dont la
        # fermeture a échoué n'aurait plus jamais de prix. Zone à ±35 % : avec
        # une volatilité de 20 % et plus, les ailes sortent des ±12 % du
        # collecteur, et le desk refuserait d'ouvrir quand la prime est la
        # plus grosse.
        ouvertes = {b.echeance for b in livre.barreaux}
        choisir = lambda exps: sorted(set(choisir_echeances(exps, aujourd_hui, 25, 35)) | (
            ouvertes & set(exps)))
        chaine = collecter_symbole(ib, "XSP", aujourd_hui, DOSSIER / "chaines.csv",
                                   choisir=choisir, zone_large=ZONE_SEANCE)
        (DOSSIER / "chaines").mkdir(parents=True, exist_ok=True)
        chaine.to_parquet(DOSSIER / "chaines" / f"{aujourd_hui}_{moment.replace(':', 'h')}.parquet")
        spot = float(chaine["spot"].iloc[0])

        plan = dc.planifier(livre, chaine, spot, vl, aujourd_hui, moment, rap.ok, rap.resume())
        for role, texte in plan.messages:
            dire(role, texte, "critical" if plan.bloque else "info")
        if plan.bloque:
            return 1

        for a in plan.actions:
            if isinstance(a, dc.Fermer):
                b = a.barreau
                jambes = [(t, k, "SELL" if s > 0 else "BUY") for t, k, s in b.jambes]
                r = ex.executer_combo(ib, ex.contrat_butterfly(ib, b.echeance, jambes), b.lots,
                                      ex.paliers(a.debit_milieu, a.debit_naturel), mode,
                                      instrument=f"fermeture {b.echeance}")
                if mode == ex.MODE_REEL and r.rempli >= b.lots:
                    c = livre.fermer(b, r.prix_moyen, aujourd_hui.isoformat())
                    dire(dc.VT, f"Barreau {b.echeance} fermé à {r.prix_moyen:.2f} : "
                                f"{c.resultat_options:+,.0f} $ ({c.resultat_par_point:+.1f} par point de vol).")
                elif mode == ex.MODE_REEL and r.rempli:
                    dire(dc.VT, f"Fermeture partielle de {b.echeance} ({r.rempli}/{b.lots}) : "
                                f"le prochain rapprochement bloquera le desk.", "critical")
                else:
                    dire(dc.VT, f"Fermeture {b.echeance} : {r.statut} ({r.detail[:120]}).")

            elif isinstance(a, dc.Ouvrir):
                b = a.butterfly
                # Le Risk Manager relit toute ouverture. Pas d'avis valide = pas
                # d'ouverture (docs/desk/equipe.md, règle 3).
                autorise, motif = _relecture(ib, a, livre, chaine, spot, vl, aujourd_hui)
                dire(dc.RM, motif, "info" if autorise else "warning")
                if not autorise:
                    continue
                r = ex.executer_combo(ib, ex.contrat_butterfly(ib, b.echeance, ex.jambes_ouverture(b)),
                                      a.lots, ex.paliers(-b.credit_milieu, -b.credit_naturel), mode,
                                      instrument=f"ouverture {b.echeance}")
                if mode == ex.MODE_REEL and r.rempli:
                    livre.ouvrir(rg.Butterfly(b.echeance, b.aile_put, b.centre, b.aile_call,
                                              r.rempli, aujourd_hui.isoformat(), -r.prix_moyen,
                                              b.vega_lot, b.perte_max_lot, b.iv_atm))
                    dire(dc.VT, f"Barreau {b.echeance} ouvert : {r.rempli} lot(s), "
                                f"crédit {-r.prix_moyen:.2f}.")
                else:
                    dire(dc.VT, f"Ouverture {b.echeance} : {r.statut}"
                                f"{f', marge {r.marge_initiale:,.0f} $' if r.marge_initiale else ''}.")

        n, d, msg = dc.couverture(livre, chaine, spot, aujourd_hui)
        dire(dc.ET, msg)
        if n:
            r = ex.executer_mes(ib, n, mode, aujourd_hui)
            if r and mode == ex.MODE_REEL and r.rempli:
                livre.mes_trade(r.instrument.split()[-1], r.rempli if n > 0 else -r.rempli)
                dire(dc.ET, f"{r.rempli} MES {'achetés' if n > 0 else 'vendus'} à {r.prix_moyen}.")
            elif r:
                dire(dc.ET, f"MES : {r.statut} ({r.detail[:120]}).")

        livre.noter_vl(vl)
        if mode == ex.MODE_REEL:
            rg.sauver(livre, livre_chemin)
        dire(dc.MO, f"Fin de séance. Valeur liquidative {vl:,.0f} $, "
                    f"{len(livre.barreaux)} barreau(x) ouverts, {len(livre.cycles)} fermés.")
        return 0
    except Exception as e:
        dire(dc.MO, f"Séance interrompue : {e}", "critical")
        raise
    finally:
        ib.disconnect()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Une séance du desk de volatilité.")
    # « 1030 » et « 1530 » : la forme sans deux-points des noms d'instance
    # systemd (milan-desk@1030.service).
    p.add_argument("moment", choices=["10:30", "15:30", "1030", "1530"])
    m = p.parse_args(argv).moment
    return seance(m if ":" in m else f"{m[:2]}:{m[2:]}")


if __name__ == "__main__":
    sys.exit(main())
