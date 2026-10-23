/* Rapports et décisions : ce que l'équipe a écrit pour le CIO, et les leçons qui attendent sa décision. */
import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, X } from '@phosphor-icons/react'
import { useDecision, usePropositions, useRapports, type Proposition } from '../api'
import { Carte, EnTete, Erreur, Pastille, Squelette, Vide } from '../composants/base'
import { Memo } from '../composants/memo'
import { heureParis, jour, nomTache } from '../format'

function Decision({ p }: { p: Proposition }) {
  const [rejet, setRejet] = useState(false)
  const [raison, setRaison] = useState('')
  const d = useDecision()
  const decider = (valider: boolean) => d.mutate({ id: p.id, valider, raison })
  return (
    <motion.li layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
      className="carte p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pastille ton="accent">{p.membre}</Pastille>
        {p.change_une_regle && <Pastille ton="attention">Change une règle écrite</Pastille>}
        <span className="chiffres text-[12.5px] text-encre-3">{p.id}</span>
      </div>
      <p className="mt-3 text-[15.5px] leading-relaxed text-encre">{p.lecon}</p>
      <p className="mt-2 text-[14px] leading-relaxed text-encre-2"><strong className="text-encre">Pourquoi.</strong> {p.justification}</p>
      {p.test_automatique && <p className="mt-1.5 text-[14px] text-encre-2"><strong className="text-encre">Test proposé.</strong> {p.test_automatique}</p>}
      {rejet && (
        <div className="mt-4 flex flex-col gap-2">
          <label htmlFor={`raison-${p.id}`} className="text-[13px] font-semibold text-encre">Raison du rejet</label>
          <textarea id={`raison-${p.id}`} value={raison} onChange={(e) => setRaison(e.target.value)} rows={2}
            className="rounded-[10px] border border-ligne-forte bg-surface px-3 py-2 text-[14px] text-encre outline-none focus:border-accent" />
        </div>
      )}
      {d.error && <p className="mt-3 text-[13px] text-alerte" role="alert">{String((d.error as Error).message)}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        {!rejet ? (
          <>
            <button onClick={() => decider(true)} disabled={d.isPending}
              className="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-4 py-2 text-[14px] font-semibold text-accent-encre transition-transform active:scale-[0.98] disabled:opacity-60">
              <Check size={15} weight="bold" /> Valider
            </button>
            <button onClick={() => setRejet(true)} disabled={d.isPending}
              className="inline-flex items-center gap-1.5 rounded-[10px] border border-ligne-forte px-4 py-2 text-[14px] font-semibold text-encre-2 hover:text-encre">
              <X size={15} weight="bold" /> Rejeter
            </button>
          </>
        ) : (
          <>
            <button onClick={() => decider(false)} disabled={d.isPending || !raison.trim()}
              className="rounded-[10px] bg-encre px-4 py-2 text-[14px] font-semibold text-page disabled:opacity-40">Confirmer le rejet</button>
            <button onClick={() => setRejet(false)} className="rounded-[10px] px-4 py-2 text-[14px] font-semibold text-encre-2">Annuler</button>
          </>
        )}
      </div>
    </motion.li>
  )
}

export default function Rapports() {
  const r = useRapports()
  const p = usePropositions()
  const [choisi, setChoisi] = useState(0)
  const attente = p.data?.filter((x) => x.statut === 'en_attente') ?? []
  const decidees = p.data?.filter((x) => x.statut !== 'en_attente') ?? []

  return (
    <>
      <EnTete titre="Rapports et décisions" sous="Le rapport du soir, la revue du vendredi, les post-mortems. Et les leçons de l'Audit, qui n'entrent dans les carnets qu'avec l'accord du CIO." />

      <section className="mb-10">
        <h2 className="titre mb-4 text-[21px] font-semibold">
          À décider {attente.length > 0 && <span className="chiffres ml-1 text-accent">{attente.length}</span>}
        </h2>
        {p.error ? <Erreur erreur={p.error} /> : p.isLoading ? <Squelette className="h-32" /> : attente.length === 0 ? (
          <Vide titre="Aucune leçon en attente">L'Audit propose ses leçons après un post-mortem ou la revue du vendredi.</Vide>
        ) : (
          <ul className="grid gap-4 lg:grid-cols-2"><AnimatePresence>{attente.map((x) => <Decision key={x.id} p={x} />)}</AnimatePresence></ul>
        )}
        {decidees.length > 0 && (
          <details className="mt-5">
            <summary className="cursor-pointer text-[14px] font-semibold text-encre-2">{decidees.length} décision{decidees.length > 1 ? 's' : ''} déjà prise{decidees.length > 1 ? 's' : ''}</summary>
            <ul className="mt-3 flex flex-col gap-2">
              {decidees.map((x) => (
                <li key={x.id} className="text-[14px] text-encre-2">
                  <Pastille ton={x.statut === 'validee' ? 'accent' : 'neutre'}>{x.statut === 'validee' ? 'Validée' : 'Rejetée'}</Pastille>{' '}
                  <span className="text-encre">{x.lecon}</span>{x.raison_cio && <span className="text-encre-3"> Raison : {x.raison_cio}</span>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section>
        <h2 className="titre mb-4 text-[21px] font-semibold">Rapports</h2>
        {r.error ? <Erreur erreur={r.error} /> : r.isLoading ? <Squelette className="h-64" /> : !r.data?.length ? (
          <Vide titre="Pas encore de rapport">Le Middle Office écrit le rapport du soir à 22 h 30, heure de Paris.</Vide>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
            <Carte as="nav" className="h-fit p-2" aria-label="Liste des rapports">
              <ul>
                {r.data.map((f, i) => (
                  <li key={f.horodatage + f.tache}>
                    <button onClick={() => setChoisi(i)} aria-current={choisi === i}
                      className={`w-full rounded-[10px] px-3 py-2.5 text-left transition-colors ${choisi === i ? 'bg-accent-doux' : 'hover:bg-surface-2'}`}>
                      <p className="text-[14px] font-semibold text-encre">{nomTache(f.tache)}</p>
                      <p className="chiffres text-[12.5px] capitalize text-encre-3">{jour(f.horodatage)}, {heureParis(f.horodatage)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </Carte>
            {r.data[choisi] && <Memo key={choisi} f={r.data[choisi]} ouvert />}
          </div>
        )}
      </section>
    </>
  )
}
