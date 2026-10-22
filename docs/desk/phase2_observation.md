# Phase 2 — Le desk réel fait-il ce que la simulation disait ?

*Protocole écrit le 2026-10-22 avec Nathan, **avant** toute ligne de la
couche options. Les résultats sont ajoutés en bas, cycle par cycle, sous des
lignes datées ; rien au-dessus ne bouge après coup. Cadre : `docs/charte.md`,
section 6, étapes 2 et 3. Preuve de rentabilité : `phase1bis_vente_variance.md`
(36 ans). Instruments vérifiés : `etape1_instruments.md`.*

---

## 1. Ce que ce test peut prouver, et ce qu'il ne peut pas

Trois mois d'observation, c'est **trois cycles d'un mois**. C'est trop peu
pour prouver une rentabilité : un seul mois de krach ou de chance déciderait
du verdict. La rentabilité est établie par la phase 1-bis, sur 440 périodes.

Ce test juge donc deux choses, à la demande de Nathan :

- **la fidélité** — le desk réel exécute, se couvre et respecte ses limites
  comme prévu, et son résultat par point de volatilité ressemble à celui de
  la simulation sur les mêmes semaines ;
- **la performance** — le desk a-t-il gagné de l'argent ? Lue avec la
  prudence qu'imposent trois cycles (section 6).

## 2. Le vendeur, règle par règle

Tout est mécanique : aucune décision n'est laissée à l'appréciation, ni de
Nathan, ni de Claude.

| Élément | Règle |
|---|---|
| **Instrument** | Options **XSP** (mini-SPX) : réglées en cash, exercice européen, même indice que le VIX. Une option SPY exercée nous livrerait des SPY, interdits au compte. |
| **Structure** | **Iron butterfly** : vente d'un put et d'un call au prix d'exercice le plus proche du cours ; achat d'un put et d'un call à **±2,5 fois le mouvement attendu** jusqu'à l'échéance, `cours × 2,5 × IV_ATM × √(jours / 365)`, arrondis vers l'extérieur au prix d'exercice existant. Les ailes sont le plafond testé en phase 1-bis. |
| **Échéance** | Le vendredi XSP le plus proche de **30 jours**, entre 25 et 35. |
| **Sortie** | Fermeture quand il reste **7 jours ou moins**, au contrôle de 10 h 30. Le cycle suivant est ouvert dans la foulée. |
| **Taille** | Nombre de lots = le plus petit de : *(a)* `0,11 % × valeur liquidative ÷ vega net d'un lot` (taille testée) ; *(b)* `2 % × valeur liquidative ÷ perte maximale d'un lot` (charte). **Aujourd'hui, (b) l'emporte : ~3 lots, soit environ un tiers de la taille testée.** Choix de Nathan : la charte reste intacte pendant l'observation. |
| **Ordre** | Un seul ordre combiné. Prix limite au milieu de la fourchette, rapproché du prix de marché par paliers toutes les 2 minutes, 3 paliers au plus ; annulé s'il n'est pas exécuté en 15 minutes, nouvel essai au contrôle suivant. |
| **Couverture** | Micro-futures **MES**. Deux contrôles par jour, **10 h 30 et 15 h 30** (New York). Si l'exposition nette au marché dépasse **un MES** (~38 500 $), on la ramène au plus près de zéro par un nombre entier de MES. Passage au contrat suivant une semaine avant l'échéance trimestrielle. |
| **Prix** | Différés de 15 minutes (pas d'abonnement OPRA). Assumé : c'est pour ça que la couverture est biquotidienne et non continue. |
| **Jour sans prix** | Férié ou panne : aucun ordre ; la journée est notée. |

**Agent couverture.** Pendant l'observation, ce sont **les ailes**. Un budget
de puts lointains en plus reste une piste pour le point d'étape (choix de
Nathan : un seul mécanisme à observer).

**Équipe Claude.** Pas encore armée (étape 6 du plan). Tant qu'elle ne l'est
pas, rien ne freine le desk en dehors des limites de la charte.

## 3. Limites de risque (charte, section 5)

Vérifiées à chaque contrôle, sans exception :

- perte depuis le plus haut **−8 %** → taille divisée par deux ; **−15 %** →
  arrêt et revue ;
- perte maximale par position **2 %** → l'ordre est refusé avant d'être
  envoyé ;
- **stress S&P −20 %** en une séance, options réévaluées, MES compris :
  perte **≤ 10 %**, sinon aucune nouvelle vente.

## 4. Période

Du jour où le desk est armé (visé : mi-décembre 2026) jusqu'à la fin du
**troisième cycle complet**. Les dates exactes sont écrites ici le jour de
l'armement, avant le premier ordre.

## 5. Ce qu'on mesure, à chaque cycle

| Mesure | Définition |
|---|---|
| **Résultat net** | Options + MES + commissions, en dollars et en % de la valeur liquidative. |
| **Résultat par point de vol** | Résultat net ÷ vega net à l'entrée. Rend le desk comparable à la simulation quelle que soit sa taille. |
| **Simulation des mêmes semaines** | Swap de variance de la phase 1-bis, entre les mêmes dates d'entrée et de sortie : `(VIX² − RV²) / (2 × VIX)`, sans frais. |
| **Frais réels** | Commissions + écart entre prix d'exécution et milieu de fourchette, ÷ vega, en points de volatilité. |
| **Tenue de la couverture** | Part des contrôles où l'exposition nette, après couverture, est restée sous un MES. |
| **Incidents** | Toute limite touchée, tout ordre non prévu, tout écart avec les positions du courtier, chacun expliqué par écrit. |

## 6. Critères

### Fidélité — tous doivent passer

| | Critère |
|---|---|
| **F1** | **Zéro** limite de la charte violée, **zéro** ordre non prévu par la section 2. |
| **F2** | **Zéro** écart inexpliqué entre nos positions et celles du courtier. |
| **F3** | Frais réels moyens **≤ 0,5 point de volatilité** par cycle (la phase 1-bis en supposait 1). |
| **F4** | Écart moyen entre le résultat par point de vol du desk et la simulation des mêmes semaines **≤ 1,5 point** par cycle. |
| **F5** | Exposition nette sous un MES après couverture dans **≥ 90 %** des contrôles. |

### Performance — choix de Nathan

| | Critère |
|---|---|
| **P1** | Résultat net cumulé **> 0** sur les trois cycles. |

**Comment lire P1.** Si le résultat est négatif, on regarde la simulation des
mêmes semaines :

- **simulation négative aussi** (le marché a été violent) → le desk a perdu
  ce que la stratégie devait perdre ; ce n'est **pas** un échec de mise en
  œuvre. C'est écrit, et ça ne déclenche aucune modification des règles
  (« si on perd, on apprend » : une perte normale ne s'apprend pas, elle se
  porte) ;
- **simulation positive, desk négatif** → **échec** : quelque chose dans
  l'exécution ne marche pas, et on le cherche avant toute suite.

### Verdict

- **F1 à F5 passent et P1 passe ou s'explique** → le point d'étape décide de la
  vraie taille (y compris la limite de 2 % et la question des 20 %/an), du
  pod n°2, du site et de la lettre.
- **Un critère F échoue** → on corrige la mise en œuvre et on recommence une
  observation de trois cycles. Chaque vraie erreur devient un test
  automatique.

## 7. Limites connues, écrites avant

- **Trois cycles** : P1 ne prouve rien seul, d'où sa lecture conditionnée.
- **Un tiers de la taille testée** : les dollars gagnés ou perdus seront trois
  fois plus petits que ce que montrait la phase 1-bis à taille charte.
- **Exécutions simulées** : le compte paper d'IBKR remplit les ordres selon
  ses propres règles, souvent plus généreuses que le vrai marché. F3 est donc
  plutôt optimiste.
- **Prix différés** : la couverture réagit avec au moins 15 minutes de retard
  — un choc rapide en séance n'est couvert qu'au contrôle suivant.
- **Le swap de variance n'est pas l'iron butterfly** : ailes, sortie à 7
  jours et couverture discrète les font diverger, même sans erreur. F4
  tolère 1,5 point pour cette raison ; ce seuil est un jugement, pas une
  statistique.

---

## Amendement 1 — 2026-10-22, avant l'armement : l'échelle hebdomadaire

*Décidé avec Nathan après le rapport du 2026-10-22. Ajouté sous le protocole
d'origine, qui reste lisible tel qu'il a été commité (65f74d7). Aucune
position n'a encore été ouverte : l'amendement ne peut s'appuyer sur aucun
résultat.*

**Pourquoi.** Le protocole d'origine ouvrait tout le livre le même jour, une
fois toutes les trois semaines : un seul pari sur le timing. La phase 1-bis a
montré que le résultat dépend fortement du jour de départ (9 départs sur 21
ont pris mars 2020 de plein fouet). Étaler les ouvertures dans le temps
diversifie ce risque, et donne au desk le flux régulier que Nathan demandait.
C'est la même stratégie, mieux répartie : ce qu'a mesuré la phase 1-bis, en
moyenne sur les départs.

**Ce qui remplace les lignes Échéance, Sortie et Taille de la section 2 :**

| Élément | Règle |
|---|---|
| **Barreau** | Chaque semaine, au contrôle de 10 h 30 du premier jour de bourse de la semaine, le desk ouvre **un** iron butterfly (même structure, mêmes ailes) sur le vendredi XSP le plus proche de 30 jours, entre 25 et 35. |
| **Sortie** | À chaque contrôle, tout barreau à **7 jours ou moins** est fermé. Chaque barreau vit donc environ trois semaines : **3 à 4 barreaux** ouverts en même temps. |
| **Taille d'un barreau** | **1 lot**, l'unité minimale d'XSP. Il est ouvert seulement si, barreau compris : sa perte maximale ≤ 2 % de la valeur liquidative ; le vega total du livre ≤ 0,11 % de la valeur liquidative par point (taille testée) ; le stress −20 % ≤ 10 %. |
| **État « réduire » (−8 %)** | Pas de nouveau barreau tant que le livre en compte 2 ou plus. Avec des barreaux d'un lot, c'est la façon la plus proche de « diviser la taille par deux » : le livre se réduit de lui-même en deux à trois semaines. |
| **État « arrêt » (−15 %)** | Aucun nouveau barreau ; les barreaux ouverts vont à leur sortie, la couverture continue. |

**Ordre de grandeur, sur la photo XSP du 2026-10-22 :** 3 à 4 barreaux d'un
lot, soit un vega de 420 à 560 $ par point (0,04 à 0,05 % de la valeur
liquidative, sous la taille testée) et une perte maximale totale de 18 000 à
24 000 $ (1,8 à 2,3 %).

**Ce qui change dans la mesure.** L'unité de mesure de la section 5 devient le
**barreau** : chacun a sa date d'entrée, sa date de sortie, son vega, sa
simulation des mêmes semaines. Sur trois mois, une dizaine de barreaux fermés
au lieu de trois cycles : F3 et F4 reposent sur plus d'observations. P1 se lit
sur le résultat net cumulé du compte, inchangé. La période d'observation va
de l'armement jusqu'à la fermeture du dixième barreau.

**Rien d'autre ne change** : instrument, structure, ailes, couverture, limites,
critères.
