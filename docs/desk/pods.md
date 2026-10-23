# Les deux nouveaux pods : prop trader et acheteur de volatilité

*Écrit le 2026-10-23, à la décision du CIO (charte, amendement 1). Règles
fixées avant le code ; ce qui change ensuite change ici d'abord, daté.*

Les deux pods sont **armés en paper trading dès leur mise en service** : le
CIO a choisi d'apprendre en tradant plutôt que d'attendre trois mois. Leur
jugement se fait vers l'avenir, trade par trade, à partir du premier jour.

---

## 1. Le prop trader

Un agent Claude qui lit le marché américain chaque jour et décide de trades
sur les actions du S&P 500, à l'achat comme à la vente à découvert.

### Quand il travaille (heure de New York)

| Heure | Tâche |
|---|---|
| 9 h 45 | **Ouverture** : il lit le marché, propose ses trades, revoit ses positions. |
| 12 h 30 | **Suivi** : il revoit ses positions (sortir, déplacer un stop) et peut ouvrir si des places sont libres. |
| 16 h 10 | **Clôture** (code seul, sans Claude) : enregistre les stops et objectifs exécutés dans l'après-midi et le résultat du jour du pod. |

Les stops et les objectifs sont posés **chez IBKR** à l'entrée : ils protègent
la position en continu, entre deux passages, même si le serveur tombe.

### Ce qu'il voit (outils en lecture seule, chiffres calculés par le code)

- **L'écran du marché** : pour les 500 titres, rendements à 1, 5 et 20 jours,
  momentum à 3 mois, ADX, écart aux moyennes mobiles 50 et 200 jours, RSI,
  volatilité ; les titres qui sortent du lot ; la performance des secteurs.
- **La fiche d'un titre** : ses indicateurs, ses cours récents, ses prochains
  résultats et dividendes, les titres de presse qui le citent.
- **L'actualité** : les titres des sources du fonds, le briefing et les
  analyses du Research Analyst.
- **Son livre** : positions, résultat du jour, ses derniers trades et ce
  qu'ils ont donné, son carnet de leçons.

### Ce que le code vérifie avant tout ordre (budget du CIO)

| Règle | Seuil |
|---|---|
| Titres autorisés | Membres du S&P 500 du jour ; jamais un ETF (interdit au compte) |
| Positions ouvertes | 8 au plus |
| Taille d'une position | 8 % de la valeur liquidative au plus |
| Risque d'un trade | (entrée − stop) × quantité ≤ **1 %** de la valeur liquidative |
| Stop | Obligatoire, du bon côté du prix, à moins de 15 % de l'entrée |
| Prix d'entrée | Ordre limite à moins de 1 % du dernier cours |
| Journée | Si le pod perd 2 % de la valeur liquidative dans la séance : plus d'ouverture jusqu'au lendemain (les sorties restent permises) |
| Limites du fonds | À −8 % : tailles divisées par deux ; à −15 % : aucune ouverture |

La **quantité** est calculée par le code : la plus petite de celle que permet
le risque de 1 % et de celle que permet la taille demandée par l'agent.

**Relecture.** Le Risk Manager relit le lot de trades proposés à chaque
passage et peut en freiner une partie. Sans avis valide : aucune ouverture
(les sorties restent permises). Un trade du lot qu'il ne mentionne pas est
freiné. Une alerte du Research Analyst ne freine **pas** le pod d'office,
comme elle le fait pour le vendeur : un jour de choc peut être une occasion
pour un trader directionnel. Le Risk Manager la voit et en juge.

**Modèle.** Le Prop Trader et sa relecture tournent sur **Opus 5.5** : c'est
le seul membre qui décide des trades. Coût mesuré à la première répétition
(2026-10-23) : 1,56 $ pour le Prop Trader (6 tours, 6 recherches web) et
0,35 $ pour la relecture, soit près de 2 $ par passage avec ouvertures —
jusqu'à 80 $ par mois à deux passages par jour. Revu après la première
semaine.

**Ajustements.** Sortir est toujours permis. Déplacer le stop l'est tant que
le risque restant ne dépasse pas 1 % de la valeur liquidative ; l'objectif,
tant qu'il reste du bon côté du cours.

### Comment il sera jugé

Trade par trade, écrit par le code : résultat en dollars et en multiples du
risque pris (« R »), taux de réussite, résultat du pod jour par jour comparé
au S&P 500, frais. L'Audit le passe en revue chaque vendredi avec le reste de
l'équipe. Le CIO ajuste quand il le juge utile ; chaque ajustement est daté
ici.

**Limite connue, écrite avant :** dans la v1, le momentum, l'ADX et les
moyennes mobiles **seuls** n'avaient montré aucun avantage
(`docs/verdicts_agents.md`). Le pari du pod est que le raisonnement sur
l'actualité apporte ce que les indicateurs n'apportaient pas. C'est ce que la
mesure dira.

---

## 2. L'acheteur de volatilité

Il achète un straddle (un call et un put au même prix d'exercice) juste avant
les résultats d'une grande société, **seulement quand les options
sous-estiment le mouvement que cette société fait d'habitude ce jour-là**.

| Élément | Règle |
|---|---|
| Univers | Les 50 plus grandes sociétés du S&P 500 (volume échangé en dollars) |
| Déclencheur | Résultats publiés après la clôture du jour ou avant l'ouverture du lendemain |
| Mouvement prévu | Prix du straddle à la monnaie (milieu de fourchette, première échéance qui expire **après** le jour de réaction) ÷ cours |
| Mouvement habituel | Moyenne du mouvement absolu de l'action sur ses 8 derniers résultats (clôture avant → clôture après) |
| Achat | Si le mouvement prévu < **85 %** du mouvement habituel (au moins 4 résultats passés pour juger) |
| Taille | Prime ≤ **0,5 %** de la valeur liquidative par straddle ; **2 %** au total en cours |
| Entrée | Séance de 15 h 30 (New York), ordre combiné, paliers du milieu au prix affiché |
| Sortie | Séance de 10 h 30 du lendemain, quoi qu'il arrive |
| Perte maximale | La prime payée, connue à l'achat |
| Décision | Code seul, sans Claude ni relecture : la règle est entièrement écrite ici |

**Limite connue, écrite avant :** acheter de la volatilité perd en moyenne (la
phase 1-bis l'a montré du côté vendeur). La règle ne parie que sur les cas où
le marché paie le mouvement moins cher que d'habitude. Ce filtre n'a pas été
testé sur le passé ; il est mesuré vers l'avenir, résultat par résultat.

---

## 3. Le compte partagé

Les trois pods vivent dans le même compte paper. Chacun tient son registre
(`logs/desk/livre.json`, `logs/prop/livre.json`, `logs/acheteur/livre.json`) ;
le Middle Office les rapproche ensemble des positions du courtier. Le
résultat de chaque pod se calcule sur ses propres positions (charte,
amendement 1).

Verrous : `PROP_ENABLED` et `ACHETEUR_ENABLED` dans `/opt/milan/.env`, en plus
d'`EXECUTION_ENABLED`. Refermer l'un d'eux remet le pod en simulation.
