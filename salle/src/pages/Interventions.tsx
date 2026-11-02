/* Ce qui attend le CIO : l'écran qu'ouvre une notification « Action requise ». */
import { useParams } from 'react-router-dom'
import { useInterventions, useReponse, type Intervention } from '../api'
import { EnTete, Erreur, Pastille, Squelette, Vide } from '../composants/base'
import { heureParis, jour } from '../format'

const FERMEE = { regle: 'Réglé par toi', je_m_en_occupe: 'Réglé', automatique: "Reparti tout seul" } as const

function Demande({ d, visee }: { d: Intervention; visee: boolean }) {
  const r = useReponse()
  const ouverte = d.statut === 'ouverte'
  const prise = d.reponse === 'je_m_en_occupe'
  return (
    <li className={`carte p-5 ${visee ? 'ring-2 ring-accent' : ''}`}>
      <div className="flex flex-wrap items-center gap-2">
        {ouverte
          ? <Pastille ton="attention">{prise ? "Tu t'en occupes" : 'À traiter'}</Pastille>
          : <Pastille>{d.reponse ? FERMEE[d.reponse] : 'Fermée'}</Pastille>}
        <span className="chiffres text-[12.5px] text-encre-3">{jour(d.signalee_le)} · {heureParis(d.signalee_le)}</span>
      </div>
      <h2 className="mt-3 text-[16px] font-semibold text-encre">{d.titre}</h2>
      <p className="mt-2 text-[15.5px] leading-relaxed text-encre">{d.texte}</p>
      {ouverte && (
        <>
          <div className="mt-4 flex flex-wrap gap-2.5">
            {!prise && (
              <button disabled={r.isPending} onClick={() => r.mutate({ id: d.id, reponse: 'je_m_en_occupe' })}
                className="rounded-[10px] border border-ligne-forte px-4 py-2.5 text-[15px] font-semibold text-encre">
                Je m'en occupe
              </button>
            )}
            <button disabled={r.isPending} onClick={() => r.mutate({ id: d.id, reponse: 'regle' })}
              className="rounded-[10px] bg-accent px-4 py-2.5 text-[15px] font-semibold text-accent-encre">
              C'est réglé
            </button>
          </div>
          <p className="mt-3 text-[13.5px] text-encre-2">
            Ta réponse n'envoie aucun ordre. « Je m'en occupe » coupe les rappels. Si le problème est toujours là
            après « C'est réglé », une nouvelle demande s'ouvrira.
          </p>
          {r.error && <p className="mt-2 text-[14px] text-alerte" role="alert">{(r.error as Error).message}</p>}
        </>
      )}
    </li>
  )
}

export default function Interventions() {
  const { id } = useParams()
  const { data, isLoading, error } = useInterventions()
  if (error) return <Erreur erreur={error} />
  const toutes = data ?? []
  const visee = toutes.find((d) => d.id === id)
  const ouvertes = toutes.filter((d) => d.statut === 'ouverte')
  // Une notification ancienne dont la demande est fermée la montre quand même, en tête.
  const liste = visee && visee.statut !== 'ouverte' ? [visee, ...ouvertes] : ouvertes
  const fermees = toutes.filter((d) => d.statut !== 'ouverte' && d !== visee).slice(0, 10)
  return (
    <>
      <EnTete titre="Interventions" sous="Ce qui attend ta réponse." />
      {isLoading && <Squelette className="h-40 w-full" />}
      {!isLoading && !liste.length && <Vide titre="Rien à traiter">Aucun pod n'attend de réponse.</Vide>}
      <ul className="flex flex-col gap-4">
        {liste.map((d) => <Demande key={d.id} d={d} visee={d.id === id} />)}
      </ul>
      {fermees.length > 0 && (
        <>
          <p className="etiquette mb-3 mt-8">Fermées récemment</p>
          <ul className="flex flex-col gap-4">{fermees.map((d) => <Demande key={d.id} d={d} visee={false} />)}</ul>
        </>
      )}
    </>
  )
}
