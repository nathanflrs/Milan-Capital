/* La porte d'entrée : le logo, et la connexion. */
import { useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { connecter } from '../api'
import { Arcade } from '../composants/base'

export default function Connexion({ connecte }: { connecte: () => void }) {
  const [id, setId] = useState('')
  const [mdp, setMdp] = useState('')
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)
  const reduit = useReducedMotion()

  const soumettre = async (e: React.FormEvent) => {
    e.preventDefault()
    setEnvoi(true); setErreur(null)
    try { await connecter(id, mdp); connecte() } catch (x) { setErreur((x as Error).message) } finally { setEnvoi(false) }
  }

  return (
    <div className="grid min-h-[100dvh] bg-page lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-[var(--nuit-panneau)] p-12 text-[var(--nuit-panneau-encre)] lg:flex">
        <p className="etiquette !text-white/55">Milan Capital / Salle des marchés</p>
        <motion.div initial={reduit ? false : { opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}>
          <Arcade className="h-auto w-[300px] text-white" />
          <h1 className="titre mt-10 max-w-[14ch] text-[46px] font-semibold leading-[1.08]">Un desk de volatilité, tenu par une équipe.</h1>
        </motion.div>
        <p className="max-w-[46ch] text-[14px] leading-relaxed text-white/60">
          Paper trading sur Interactive Brokers. Chaque décision est écrite, chaque chiffre vient d'un journal.
        </p>
      </section>
      <section className="flex items-center justify-center px-6 py-16">
        <form onSubmit={soumettre} className="w-full max-w-[360px]">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <Arcade className="h-7 w-auto text-encre" />
            <span className="titre text-[24px] font-semibold">Milan Capital</span>
          </div>
          <h2 className="titre text-[28px] font-semibold">Connexion</h2>
          <p className="mt-1.5 text-[15px] text-encre-2">Réservée au CIO.</p>
          <div className="mt-8 flex flex-col gap-2">
            <label htmlFor="id" className="text-[14px] font-semibold text-encre">Identifiant</label>
            <input id="id" autoComplete="username" value={id} onChange={(e) => setId(e.target.value)} required
              className="rounded-[10px] border border-ligne-forte bg-surface px-3.5 py-2.5 text-[15px] text-encre outline-none focus:border-accent" />
          </div>
          <div className="mt-5 flex flex-col gap-2">
            <label htmlFor="mdp" className="text-[14px] font-semibold text-encre">Mot de passe</label>
            <input id="mdp" type="password" autoComplete="current-password" value={mdp} onChange={(e) => setMdp(e.target.value)} required
              className="rounded-[10px] border border-ligne-forte bg-surface px-3.5 py-2.5 text-[15px] text-encre outline-none focus:border-accent" />
          </div>
          {erreur && <p className="mt-4 text-[14px] text-alerte" role="alert">{erreur}</p>}
          <button disabled={envoi}
            className="mt-7 w-full rounded-[10px] bg-accent py-3 text-[15px] font-semibold text-accent-encre transition-transform active:scale-[0.99] disabled:opacity-60">
            {envoi ? 'Connexion…' : 'Entrer'}
          </button>
        </form>
      </section>
    </div>
  )
}
