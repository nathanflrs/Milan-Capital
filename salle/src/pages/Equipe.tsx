/* L'équipe : chaque membre dans sa niche en arche, avec son voyant en direct. */
import { motion, useReducedMotion } from 'motion/react'
import { Link } from 'react-router-dom'
import { Brain, Code, User } from '@phosphor-icons/react'
import { useEquipe, type Membre } from '../api'
import { Carte, EnTete, Erreur, Pastille, Squelette, Voyant } from '../composants/base'
import { dans, dollars, ilYa, nomTache } from '../format'

const INITIALES: Record<string, string> = {
  CIO: 'CIO', 'Volatility Trader': 'VT', 'Execution Trader': 'ET', 'Risk Manager': 'RM',
  'Research Analyst': 'RA', 'Middle Office': 'MO', Audit: 'AU',
}

function Niche({ membre }: { membre: Membre }) {
  const actif = membre.statut === 'au_travail'
  return (
    <div className={`arche flex h-[104px] w-[84px] shrink-0 flex-col items-center justify-end pb-3 ${
      membre.nature === 'humain' ? 'bg-[var(--nuit-panneau)] text-[var(--nuit-panneau-encre)]'
        : actif ? 'bg-accent text-accent-encre' : 'bg-surface-2 text-encre'}`}>
      <span className="titre text-[22px] font-semibold leading-none">{INITIALES[membre.titre]}</span>
    </div>
  )
}

function Nature({ membre }: { membre: Membre }) {
  if (membre.nature === 'humain') return <Pastille><User size={12} weight="bold" className="mr-1" />Humain</Pastille>
  if (membre.nature === 'code') return <Pastille><Code size={12} weight="bold" className="mr-1" />Code testé</Pastille>
  return <Pastille ton="accent"><Brain size={12} weight="bold" className="mr-1" />Claude {membre.modele}</Pastille>
}

function CarteMembre({ membre, i }: { membre: Membre; i: number }) {
  const reduit = useReducedMotion()
  const d = membre.derniere_action
  return (
    <motion.div initial={reduit ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}>
      <Link to={membre.titre === 'CIO' ? '/rapports' : `/equipe/${membre.slug}`}
        className="carte group flex h-full gap-5 p-5 transition-transform hover:-translate-y-0.5 active:translate-y-0">
        <Niche membre={membre} />
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="titre text-[19px] font-semibold leading-tight">{membre.titre}</p>
            {membre.titre !== 'CIO' && <Voyant statut={membre.statut} />}
          </div>
          <div className="mt-1.5"><Nature membre={membre} /></div>
          <p className="mt-3 text-[14px] leading-snug text-encre-2">
            {d ? <>{d.message}</> : membre.mission}
          </p>
          <div className="chiffres mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-4 text-[12.5px] text-encre-3">
            {d && <span>{nomTache(d.tache)} · {ilYa(d.heure_utc)}</span>}
            {membre.prochaine_tache && <span>Prochain : {membre.prochaine_tache.tache}, {dans(membre.prochaine_tache.a)}</span>}
            {membre.cout_du_jour_usd > 0 && <span>{dollars(membre.cout_du_jour_usd)} aujourd'hui</span>}
          </div>
        </div>
      </Link>
    </motion.div>
  )
}

export default function Equipe() {
  const { data, error, isLoading } = useEquipe()
  if (error) return <Erreur erreur={error} />
  const travaillent = data?.filter((m) => m.statut === 'au_travail').length ?? 0
  return (
    <>
      <EnTete titre="L'équipe"
        sous={<>Deux membres en code testé, quatre membres Claude, un CIO. Les membres Claude lisent, raisonnent et
          rendent un mémo : aucun ne passe d'ordre. {travaillent > 0 && <strong className="text-encre">{travaillent} au travail en ce moment.</strong>}</>} />
      {isLoading || !data ? (
        <div className="grid gap-5 lg:grid-cols-2">{Array.from({ length: 6 }, (_, i) => <Squelette key={i} className="h-40" />)}</div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {data.map((m, i) => <CarteMembre key={m.titre} membre={m} i={i} />)}
        </div>
      )}
      <Carte className="mt-8 p-6">
        <p className="titre text-[17px] font-semibold">Comment l'équipe est tenue</p>
        <p className="mt-2 max-w-[75ch] text-[14px] leading-relaxed text-encre-2">
          Le Risk Manager ne peut que freiner une ouverture, jamais en ajouter. Sans avis valide, pas d'ouverture.
          Une alerte du Research Analyst freine d'office. L'Audit propose des leçons, et seul le CIO les fait entrer
          dans les carnets que chaque membre relit.
        </p>
      </Carte>
    </>
  )
}
