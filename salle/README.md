# La salle des marchés

L'application de Milan Capital : le desk, l'équipe au travail en direct, le
fil, les rapports et les décisions du CIO, le protocole. React 19 +
TypeScript + Vite + Tailwind 4, charte « Double Arcade » (`../design/`).

Elle est servie par le serveur FastAPI existant (`src/dashboard/server.py`) à
l'adresse principale ; l'ancien tableau de bord reste à `/v1`. Toutes les
données viennent de `/api/salle/*` (`src/dashboard/salle.py`), qui lit les
journaux écrits par le code du fonds. Le direct passe par
`/api/events/stream` : téléphone et Mac affichent la même chose à la seconde.

## Compiler et déployer

Le serveur de production n'a pas Node : on compile ici, et la compilation
(`src/dashboard/salle_dist/`) est commitée.

```bash
npm install
npm run build          # → ../src/dashboard/salle_dist
```

Puis commit, push, et sur le serveur : `git pull` et
`systemctl restart milan-dashboard`.

## Développer sans serveur

`npm run dev:demo` ouvre la salle sur `src/demo.json`, un instantané des vraies
données du serveur, sans connexion. Ce fichier n'est pas dans le dépôt (le
dépôt est public) ; il se régénère avec les fonctions de `salle.py` appelées
sur le serveur (`etat()`, `equipe()`, `rapports()`, `protocole()`,
`historique(<membre>)`).
