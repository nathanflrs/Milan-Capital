import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// La salle des marchés est servie par le serveur FastAPI existant
// (src/dashboard/server.py) : la compilation part dans src/dashboard/salle_dist,
// commitée, car le serveur de production n'a pas Node.
//
// En développement : `npm run dev` avec VITE_DEMO=1 lit un jeu de données tiré
// des vrais journaux (src/demo.json), sans connexion au serveur.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../src/dashboard/salle_dist',
    emptyOutDir: true,
    assetsDir: 'salle-assets',
  },
  server: { port: 5173 },
})
