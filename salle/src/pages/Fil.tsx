/* Le fil : tout ce que font le desk et l'équipe, en direct, filtrable par membre. */
import { useMemo, useState } from 'react'
import { useFil, type Evenement } from '../api'
import { EnTete, Erreur, Squelette, Vide } from '../composants/base'
import { cents, heureNY, heureParis, jour, nomTache } from '../format'

const MEMBRES = ['Tous', 'Research Analyst', 'Risk Manager', 'Volatility Trader', 'Execution Trader', 'Middle Office', 'Audit', 'CIO']

function Ligne({ e }: { e: Evenement }) {
  const debut = e.phase === 'debut'
  const marque = e.gravite === 'critical' ? 'bg-alerte' : e.gravite === 'warning' ? 'bg-attention'
    : debut ? 'bg-accent' : 'bg-ligne-forte'
  return (
    <li className="grid grid-cols-[64px_14px_1fr] gap-3">
      <div className="chiffres pt-0.5 text-right">
        <p className="text-[14px] font-semibold text-encre">{heureParis(e.heure_utc)}</p>
        <p className="text-[11.5px] text-encre-3">{heureNY(e.heure_utc)} NY</p>
      </div>
      <div className="relative flex justify-center">
        <span className="absolute inset-y-0 w-px bg-ligne" />
        <span className={`relative mt-1.5 size-2.5 rounded-full ring-4 ring-page ${marque}`} aria-hidden />
      </div>
      <div className={`min-w-0 pb-6 ${debut ? 'opacity-70' : ''}`}>
        <p className="text-[13px] font-semibold text-encre">
          {e.qui} {e.tache && <span className="font-normal text-encre-3">· {nomTache(e.tache)}</span>}
        </p>
        <p className="mt-0.5 text-[14.5px] leading-snug text-encre-2">{e.message}</p>
        {e.cout_usd ? <p className="chiffres mt-0.5 text-[12px] text-encre-3">{cents(e.cout_usd)}</p> : null}
      </div>
    </li>
  )
}

export default function Fil() {
  const [jours, setJours] = useState(2)
  const [qui, setQui] = useState('Tous')
  const { data, error, isLoading } = useFil(jours)
  const parJour = useMemo(() => {
    const g = new Map<string, Evenement[]>()
    for (const e of (data ?? []).filter((x) => qui === 'Tous' || x.qui === qui)) {
      const j = jour(e.heure_utc)
      g.set(j, [...(g.get(j) ?? []), e])
    }
    return [...g.entries()]
  }, [data, qui])

  return (
    <>
      <EnTete titre="Le fil" sous="Chaque action du desk et de l'équipe, au moment où elle a lieu. Se met à jour tout seul." />
      <div className="mb-8 flex flex-wrap items-center gap-2" role="group" aria-label="Filtrer par membre">
        {MEMBRES.map((m) => (
          <button key={m} onClick={() => setQui(m)} aria-pressed={qui === m}
            className={`rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors ${
              qui === m ? 'bg-encre text-page' : 'bg-surface-2 text-encre-2 hover:text-encre'}`}>{m}</button>
        ))}
      </div>
      {error ? <Erreur erreur={error} /> : isLoading ? (
        <div className="grid gap-4">{Array.from({ length: 5 }, (_, i) => <Squelette key={i} className="h-12" />)}</div>
      ) : parJour.length === 0 ? (
        <Vide titre="Rien sur la période">Le fil se remplit dès la prochaine tâche : briefing à 14 h 30, heure de Paris.</Vide>
      ) : (
        <div className="max-w-[860px]">
          {parJour.map(([j, evts]) => (
            <section key={j} className="mb-6">
              <h2 className="titre mb-4 text-[18px] font-semibold capitalize">{j}</h2>
              <ol>{evts.map((e, i) => <Ligne key={e.heure_utc + i} e={e} />)}</ol>
            </section>
          ))}
          <button onClick={() => setJours(Math.min(jours + 5, 14))} disabled={jours >= 14}
            className="rounded-[10px] border border-ligne-forte px-4 py-2 text-[14px] font-semibold text-encre-2 hover:text-encre disabled:opacity-40">
            Remonter plus loin
          </button>
        </div>
      )}
    </>
  )
}
