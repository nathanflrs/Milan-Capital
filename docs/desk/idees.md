# Registre des idées — pour le point d'étape

*Ouvert le 2026-10-22. La charte interdit de changer de cap avant le point
d'étape (avril 2027) : toute idée nouvelle atterrit ici au lieu d'interrompre
le desk. Au point d'étape, on en choisit une, on écrit son protocole, on la
teste — dans cet ordre, jamais l'inverse (docs/charte.md, section 2).*

**Comment lire une fiche.** Une idée n'est retenue que si elle a une raison
économique de payer (*qui nous paie, et pourquoi ?*), des données pour la
tester avant d'écrire du code, et un risque qu'on sait nommer. Le critère qui
compte le plus pour le pod n°2 : **gagne-t-elle quand le vendeur de
volatilité perd ?** Deux stratégies qui se protègent l'une l'autre valent
mieux que deux bonnes stratégies qui perdent le même jour.

---

## 1. Le calendar spread — la structure par terme de la volatilité

*Proposée par Nathan le 2026-10-22.*

| | |
|---|---|
| **Le trade** | Vendre une option à échéance courte, acheter la même (même prix d'exercice) à échéance plus longue. |
| **Qui nous paie** | En temps normal, la volatilité implicite courte est plus basse que la longue, et l'option courte perd sa valeur-temps plus vite : on encaisse cette différence d'usure. C'est une prime **différente** de la prime de variance du desk actuel — un pari sur la *forme* de la courbe des volatilités, pas sur son niveau. |
| **Données pour tester** | Gratuites, au CBOE : VIX à 9 jours (VIX9D, depuis 2011), à 30 jours (VIX, 1990) et à 3 mois (VIX3M, 2007). On peut rejouer la pente de la courbe sur 15 à 20 ans, comme la phase 1-bis. Puis nos propres photos de chaîne (collecteur, depuis le 2026-10-22). |
| **Le risque** | Dans un krach, la volatilité courte bondit plus que la longue (la courbe s'inverse) : le calendar **perd aussi**. Il ne protège donc pas le desk le jour du choc — à mesurer précisément, c'est la question qui décide. |
| **Pour nous** | Mêmes instruments (XSP), même infrastructure : coût de construction faible. |

## 2. Le suivi de tendance sur futures — « crisis alpha »

| | |
|---|---|
| **Le trade** | Sur un panier de contrats futures diversifiés (indices actions, taux, devises, matières premières), acheter ce qui monte depuis plusieurs mois, vendre ce qui baisse. |
| **Qui nous paie** | Les marchés intègrent les nouvelles lentement et les tendances persistent (Moskowitz, Ooi et Pedersen, *Time Series Momentum*, 2012) ; documenté sur plus d'un siècle de données (Hurst, Ooi et Pedersen, 2017). |
| **Données pour tester** | Prix des futures continus : yfinance pour un premier passage, une source payante si le test le justifie. |
| **Le risque** | Perd dans les marchés sans direction et lors des retournements brusques. Longues traversées du désert. |
| **Pour nous** | **Le meilleur candidat de complément connu** : il a tendance à gagner dans les krachs longs (2008, 2022), précisément quand la vente de volatilité perd. ⚠️ Ce n'est pas ce que faisaient les agents « tendance » de la v1 : eux achetaient seulement, sur 11 actions — et ont échoué (`docs/verdicts_agents.md`). Les MES sont déjà autorisés sur le compte ; les autres futures sont à vérifier par simulation, comme à l'étape 1. |

## 3. Le momentum de fin de journée

| | |
|---|---|
| **Le trade** | Si le S&P 500 a monté (baissé) pendant la première demi-heure, acheter (vendre) pour la dernière demi-heure. Un trade par jour au plus. |
| **Qui nous paie** | Les teneurs de marché d'options et les ETF à levier doivent se couvrir en fin de séance dans le sens du marché, ce qui pousse les prix (Gao, Han, Li et Zhou, *JFE* 2018 ; Baltussen, Da, Lammers et Martens, *JFE* 2021). Une cause liée aux **options** : le métier visé par Nathan. |
| **Données pour tester** | Barres de 30 minutes sur plusieurs années : IBKR (historique intraday, à vérifier) ou une source payante. |
| **Le risque** | L'effet est petit : les frais peuvent tout manger. Il a pu s'affaiblir depuis sa publication. |
| **Pour nous** | Du flux quotidien, avec une raison économique — la seule version du day trading qui en ait une. Exécutable en MES. |

---

## Autres pistes notées en chemin

| Idée | D'où elle vient | Statut |
|---|---|---|
| **Échelle quotidienne** (options à ~9 jours, un barreau par jour) | Demande de flux de Nathan, 2026-10-22 | Au plan (étape 4-bis), protocole à écrire — proxy VIX9D |
| **Freiner sur un bond du VIX** | Leçon de la phase 1-ter : la prime paraît la plus grosse au début d'un krach | Rôle naturel du Risk Manager ; à tester comme frein, jamais comme accélérateur |
| **Puts lointains en plus des ailes** | Choix de Nathan pour l'observation (les ailes suffisent) | Le PPUT a coûté 2,6 %/an : à ne tester qu'en combinaison avec le desk |
| **Taille du desk et objectif de 20 %/an** | Discussion du 2026-10-22 | Se décide au point d'étape, sur résultats réels |
| **Données en direct** (compte réel IBKR, abonnement OPRA) | Prix différés de 15 minutes | Avant l'échelle quotidienne, probablement indispensable |

## Écartées, avec la raison

| Idée | Pourquoi non |
|---|---|
| Short strangle (vente sans ailes) | Perte illimitée, interdit par la charte ; sans plafond, la phase 1-bis perd en Sharpe (0,77 contre 0,86). |
| Long straddle en continu | Achète la prime que le desk vend : perd en moyenne (83 % des mois pour le vendeur). Utile seulement autour d'événements, à tester. |
| Protective put en continu | PPUT : 7,8 %/an contre 10,4 % pour le S&P 500 (2001-2026), et −42 % de pire baisse. |
| Arbitrage de dividendes | Jeu de teneurs de marché ; 100 % de HOLD pour l'agent de la v1. |
| Bougies japonaises | Pas de valeur après frais (Marshall, Young et Rose, 2006) ; figures floues, propices à se tromper soi-même. |
| Levier par conviction | Phase 1-ter : double la mise au pire moment (mars 2020). |
| Prime services | Métier de banque : licence et bilan. |
