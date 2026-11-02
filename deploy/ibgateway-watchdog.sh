#!/usr/bin/env bash
# Chien de garde de la passerelle IBKR.
#
# Pourquoi il existe
# ------------------
# Le 2026-08-15 à 23h45, IB Gateway a fait son redémarrage quotidien
# obligatoire. IBKR a refusé la reconnexion une fois — un incident transitoire,
# pendant leur fenêtre de maintenance. IBC a affiché « Unrecognized Username or
# Password » et n'a JAMAIS réessayé : son log n'a plus bougé pendant cinq jours.
#
# Pendant ce temps, `systemctl is-active ibgateway` répondait « active », parce
# que le script enveloppe et le processus Java vivaient — figés sur une boîte de
# dialogue modale, sur un écran virtuel que personne ne regarde. Quatre séances
# ont été perdues (17, 18, 19, 20 août). Un simple `systemctl restart` a suffi à
# tout rétablir : les identifiants étaient bons depuis le début.
#
# La leçon n'est pas « surveiller IBC ». C'est que **la présence d'un processus
# ne prouve pas la disponibilité d'un service**. On teste donc la capacité
# réelle — le port API accepte-t-il une connexion — et non l'état systemd.
#
# Le 2026-10-26 et le 2026-11-02, le même refus de connexion a laissé le port
# ouvert : la passerelle acceptait les clients sans plus jamais leur répondre, et
# tous les pods ont perdu leur journée. Le test va donc jusqu'à une vraie réponse
# de l'API (ibgateway_api_ok.py), et il faut deux échecs de suite pour redémarrer.
set -uo pipefail

PORT="${IBGW_PORT:-4002}"
ETAT=/var/lib/milan/ibgateway-watchdog.state
ECHECS=/var/lib/milan/ibgateway-watchdog.echecs
COOLDOWN=1200          # 20 min entre deux redémarrages : évite l'emballement
                       # et laisse à IBKR le temps de sa maintenance quotidienne.

mkdir -p "$(dirname "$ETAT")"

api_repond() {
    timeout 40 /opt/milan/.venv/bin/python /opt/milan/deploy/ibgateway_api_ok.py "$PORT" 2>/dev/null
}

if api_repond; then
    rm -f "$ETAT" "$ECHECS"
    echo "ibgateway-watchdog: l'API du port $PORT répond"
    exit 0
fi

echecs=$(( $(cat "$ECHECS" 2>/dev/null || echo 0) + 1 ))
echo "$echecs" > "$ECHECS"
if [ "$echecs" -lt 2 ]; then
    echo "ibgateway-watchdog: l'API du port $PORT ne répond pas — on revérifie au prochain passage"
    exit 0
fi

maintenant=$(date +%s)
dernier=$(cat "$ETAT" 2>/dev/null || echo 0)
depuis=$(( maintenant - dernier ))

if [ "$depuis" -lt "$COOLDOWN" ]; then
    echo "ibgateway-watchdog: API muette, mais redémarrage il y a ${depuis}s — on attend"
    exit 0
fi

echo "ibgateway-watchdog: API muette → redémarrage de ibgateway"
echo "$maintenant" > "$ETAT"
systemctl restart ibgateway

sleep 100
if api_repond; then
    rm -f "$ECHECS"
    echo "ibgateway-watchdog: rétabli"
else
    # Deux causes possibles : identifiants réellement invalides, ou IBKR
    # indisponible. Le cooldown empêche de marteler le compte et de le faire
    # verrouiller ; le prochain passage réessaiera.
    echo "ibgateway-watchdog: TOUJOURS injoignable après redémarrage — intervention humaine requise"
    exit 1
fi
