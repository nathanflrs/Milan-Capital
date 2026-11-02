# src/notify/alerte.py
"""Un service a échoué (systemd, OnFailure) ou s'est terminé normalement (OnSuccess)."""
import sys

from src.notify import interventions as iv

NOMS = {"prop": "Prop trader", "acheteur": "Acheteur", "desk": "Vendeur", "equipe": "Équipe",
        "options": "Photo des options", "run": "Run v1", "market": "Collecte du marché"}


def _pod(service: str) -> tuple:
    nom = service.removeprefix("milan-").removesuffix(".service")
    pod, _, moment = nom.partition("@")
    return pod, moment


def message(service: str) -> tuple:
    pod, moment = _pod(service)
    qui = NOMS.get(pod, pod)
    if moment:
        qui = f"{qui} ({moment})"
    return (f"Action requise · {qui}",
            f"{qui} a planté : ce passage n'a rien décidé. Les ordres déjà posés chez IBKR restent "
            "actifs. À faire : rien si le prochain passage repart ; sinon, demande à Claude de regarder.")


def main(evenement: str, service: str) -> int:
    pod, _ = _pod(service)
    if evenement == "reussite":
        iv.resoudre(f"echec-{pod}")
    # Un pod qui s'arrête exprès (écart courtier) vient déjà de le dire.
    elif not iv.signalee_a_l_instant(f"{pod}-"):
        titre, corps = message(service)
        iv.demander(f"echec-{pod}", titre, corps)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
