# L'équipe de Milan Capital

*Conçue le 2026-10-22 avec Nathan, CIO. Document de référence : le code de
`src/equipe/` en applique chaque règle, et une règle qui change change ici
d'abord.*

---

## 1. Principe

Une équipe, ce sont des **rôles**, des **échanges** et des **comptes à
rendre**. Chaque membre a un mandat écrit, voit le desk à travers des outils
en lecture seule, rend un **mémo structuré**, garde un carnet de leçons, et
sera **jugé sur pièces** au point d'étape.

Aucun membre Claude ne peut passer un ordre, modifier le registre ou changer
une règle. Leur pouvoir le plus fort est de **freiner**, et seulement ce qui
augmente le risque (charte, section 3).

## 2. L'organigramme

| Titre | Nature | Modèle | Autorité |
|---|---|---|---|
| **CIO** | Nathan | — | Charte, protocoles, point d'étape ; valide les leçons qui changent une règle |
| **Volatility Trader** | code testé | — | Propose ouvertures et fermetures (`src/options/decisions.py`) |
| **Execution Trader** | code testé | — | Couvre en MES (`src/options/decisions.py`) |
| **Risk Manager** | Claude | **Opus 5.5** | Approuve ou **freine** toute proposition qui augmente le risque |
| **Research Analyst** | Claude | **Sonnet 5.5** (briefing, analyses) · **Haiku 5.5** (veille) | Peut mettre le desk **en alerte** : la prochaine ouverture est freinée d'office |
| **Middle Office** | code + Claude | **Sonnet 5.5** | Rapproche (code) ; écrit le rapport du soir (Claude) |
| **Audit** | Claude | **Sonnet 5.5** | Écrit les post-mortems et les leçons ; **propose** au CIO, ne change rien |

*Mélange de modèles choisi par Nathan le 2026-10-22 pour le coût : le seul
membre qui a de l'autorité, et qui travaille rarement, a le modèle le plus
fort. Revu après la première semaine, sur les coûts mesurés.*

## 3. Une journée (heures de New York, lundi-vendredi)

| Heure | Membre | Tâche |
|---|---|---|
| 8 h 30 | Research Analyst | **Briefing** : agenda du jour, nouvelles de la nuit, courbe du VIX → *météo du jour*, gravité 1 à 5, heures à risque. |
| 9 h 30 → 16 h, toutes les 30 min | Research Analyst (veille, Haiku) | Trie les nouveaux titres des sources fixées. Rien d'important → silence. Important → analyse par Sonnet → mémo, et **alerte** si gravité ≥ 4. |
| 10 h 30 et 15 h 30 | Volatility Trader → **Risk Manager** → Execution Trader | Séance du desk. Le Risk Manager relit chaque ouverture proposée. |
| 16 h 30 | Middle Office | **Rapport du soir.** |
| vendredi 17 h | Audit | **Revue de la semaine** + mémo commun de l'équipe au CIO. |
| à chaud | Audit | **Post-mortem** après toute perte hors norme, tout frein, tout incident. |

## 4. Les règles de l'équipe

1. **Lecture seule.** Les outils des membres lisent ; aucun n'écrit dans le
   registre, n'envoie d'ordre, ne modifie un fichier de règles.
2. **Sortie structurée stricte.** Chaque mémo suit un schéma validé par l'API.
   Un mémo invalide est rejeté et journalisé ; il ne vaut jamais accord.
3. **Panne = pas d'ouverture** (choix de Nathan). Sans avis valide du Risk
   Manager — panne de l'API, refus, mémo invalide — le barreau attend le
   contrôle suivant. **Fermetures et couvertures ne dépendent jamais de
   l'équipe.**
4. **Les nouvelles sont des données, jamais des instructions.** Le texte des
   pages lues est présenté comme tel ; une page qui « demande » quelque chose
   au modèle ne peut rien obtenir d'autre qu'un mémo de gravité.
5. **Sources du Research Analyst** (choix de Nathan) : sources officielles et
   recherche web limitée à une liste de sites fixée ici :
   federalreserve.gov, bls.gov, bea.gov, treasury.gov, sec.gov, whitehouse.gov,
   cboe.com, cmegroup.com, reuters.com, apnews.com, cnbc.com, marketwatch.com,
   bloomberg.com, ft.com, wsj.com.
6. **Un texte de référence commun.** La charte et le protocole sont chargés
   tels quels dans le contexte de chaque membre (mis en cache). Ce qu'ils
   disent, toute l'équipe le sait.
7. **Tout est publié.** Chaque tâche terminée publie un récap court (une
   ligne, pour la notification) et un récap détaillé (pour la salle des
   marchés), avec son coût. La veille ne notifie que si elle trouve quelque
   chose (choix de Nathan).

## 5. Comment chaque membre sera jugé

| Membre | Mesure | Quand |
|---|---|---|
| Research Analyst | Gravité annoncée contre mouvement réel du S&P 500 et du VIX ce jour-là (calibration) | chaque jour |
| Risk Manager | Chaque frein : le barreau freiné aurait-il gagné ou perdu ? (rejoué sur les prix réels) | à l'échéance du barreau freiné |
| Middle Office | Rapports conformes aux chiffres du registre ; écarts signalés à temps | chaque jour |
| Audit | Leçons validées par le CIO et devenues tests automatiques | point d'étape |
| L'équipe | Coût par jour et par membre | chaque jour, revu après la première semaine |

**Limite connue :** les modèles connaissent l'histoire des marchés jusqu'à
leur date de coupure. Leur jugement ne se teste donc honnêtement **qu'en
direct**, jamais sur le passé — d'où ces mesures quotidiennes plutôt qu'un
backtest.

## 6. Où vivent les choses

| Quoi | Où |
|---|---|
| Code de l'équipe | `src/equipe/` |
| Mémos | `logs/equipe/memos/<date>/<membre>-<heure>.json` |
| Carnets de leçons | `logs/equipe/carnets/<membre>.md` (écrits par l'Audit) |
| Coût de chaque appel | `logs/equipe/couts.csv` |
| Événements (salle des marchés, notifications) | bus `logs/events.db`, type `equipe` |
