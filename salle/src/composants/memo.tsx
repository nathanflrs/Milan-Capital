/* Un mémo de l'équipe, lu comme un document : la partie structurée d'abord, le compte rendu ensuite. */
import { useState } from 'react'
import { CaretDown } from '@phosphor-icons/react'
import type { MemoFichier } from '../api'
import { Pastille, Texte } from './base'
import { dollars, cents, heureParis, jour, nomTache } from '../format'

const TON_STATUT: Record<string, 'neutre' | 'accent' | 'alerte' | 'attention'> = {
  ok: 'neutre', attention: 'attention', bloquant: 'alerte',
  'perte normale': 'neutre', 'vraie erreur': 'alerte', 'à juger plus tard': 'attention', 'rien à signaler': 'neutre',
  solide: 'accent', correcte: 'neutre', 'à améliorer': 'attention', 'pas assez de données': 'neutre',
  en_echec: 'alerte', a_surveiller: 'attention', pas_encore_mesurable: 'neutre',
}

function Gravite({ g, alerte }: { g?: number; alerte?: boolean }) {
  if (g == null) return null
  return (
    <span className="inline-flex items-center gap-2">
      <span className="chiffres inline-flex items-baseline gap-0.5" aria-label={`Gravité ${g} sur 5`}>
        <span className="titre text-[26px] font-semibold leading-none">{g}</span>
        <span className="text-[13px] text-encre-3">/5</span>
      </span>
      {alerte && <Pastille ton="alerte">Alerte</Pastille>}
    </span>
  )
}

function Liste({ titre, children }: { titre: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <p className="text-[13px] font-semibold text-encre">{titre}</p>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function Structure({ f }: { f: MemoFichier }) {
  const m = f.memo!
  if (f.tache === 'relecture')
    return (
      <>
        <div className="flex flex-wrap items-center gap-3">
          <Pastille ton={m.decision === 'freiner' ? 'attention' : 'accent'}>{m.decision === 'freiner' ? 'Freiné' : 'Approuvé'}</Pastille>
          <span className="chiffres text-[13px] text-encre-3">Confiance {m.confiance}/5</span>
        </div>
        <p className="mt-3 text-[15px] leading-relaxed text-encre">{m.motif_principal}</p>
        <Liste titre="Vérifications">
          <ul className="flex flex-col gap-2.5">
            {m.verifications?.map((v: any) => (
              <li key={v.element} className="grid gap-1 sm:grid-cols-[180px_1fr] sm:gap-4">
                <span className="flex items-start gap-2 text-[14px] font-semibold text-encre">
                  <Pastille ton={TON_STATUT[v.statut]}>{v.statut}</Pastille>
                </span>
                <span className="text-[14px] text-encre-2"><strong className="text-encre">{v.element}.</strong> {v.constat}</span>
              </li>
            ))}
          </ul>
        </Liste>
        <Liste titre="Ce qui le ferait changer d'avis"><p className="text-[14px] text-encre-2">{m.ce_qui_me_ferait_changer_d_avis}</p></Liste>
      </>
    )
  if (f.tache === 'briefing' || f.tache === 'analyse')
    return (
      <>
        <Gravite g={m.gravite} alerte={m.alerte} />
        {m.regime_volatilite && <p className="mt-3 text-[14px] text-encre-2"><strong className="text-encre">Volatilité.</strong> {m.regime_volatilite}</p>}
        {m.faits_verifies && <p className="mt-3 text-[14px] text-encre-2"><strong className="text-encre">Faits vérifiés.</strong> {m.faits_verifies}</p>}
        {m.evenements_du_jour?.length > 0 && (
          <Liste titre="Agenda du jour">
            <ul className="flex flex-col gap-2">
              {m.evenements_du_jour.map((e: any, i: number) => (
                <li key={i} className="grid grid-cols-[92px_1fr_auto] items-baseline gap-3 text-[14px]">
                  <span className="chiffres text-encre-3">{e.heure_new_york}</span>
                  <span className="text-encre-2">{e.titre}</span>
                  <span className="chiffres text-[12px] text-encre-3">{e.importance}/5</span>
                </li>
              ))}
            </ul>
          </Liste>
        )}
        {m.nouvelles_cles?.length > 0 && (
          <Liste titre="Nouvelles clés">
            <ul className="flex flex-col gap-3">
              {m.nouvelles_cles.map((n: any, i: number) => (
                <li key={i} className="text-[14px]"><p className="font-semibold text-encre">{n.titre}</p>
                  <p className="text-encre-2">{n.pourquoi_ca_compte} <span className="text-encre-3">({n.source})</span></p></li>
              ))}
            </ul>
          </Liste>
        )}
        {(m.implications_pour_le_desk || m.impact_pour_le_desk) &&
          <Liste titre="Pour le desk"><p className="text-[14px] text-encre-2">{m.implications_pour_le_desk || m.impact_pour_le_desk}</p></Liste>}
        {m.signalements && <Liste titre="Signalements"><p className="text-[14px] text-encre-2">{m.signalements}</p></Liste>}
      </>
    )
  if (f.tache === 'tri')
    return (
      <>
        <Gravite g={m.gravite_max} />
        {m.retenus?.length > 0 && (
          <Liste titre={`${m.retenus.length} titre${m.retenus.length > 1 ? 's' : ''} retenu${m.retenus.length > 1 ? 's' : ''}`}>
            <ul className="flex flex-col gap-2">
              {m.retenus.map((t: any, i: number) => (
                <li key={i} className="grid grid-cols-[28px_1fr] gap-2 text-[14px]">
                  <span className="chiffres font-semibold text-encre">{t.gravite}</span>
                  <span className="text-encre-2"><span className="text-encre">{t.titre}</span> <span className="text-encre-3">({t.source})</span></span>
                </li>
              ))}
            </ul>
          </Liste>
        )}
      </>
    )
  if (f.tache === 'rapport')
    return (
      <div className="grid gap-4 text-[14px] leading-relaxed text-encre-2">
        <p><strong className="text-encre">Le fonds.</strong> {m.le_fonds}</p>
        <p><strong className="text-encre">Le desk.</strong> {m.le_desk}</p>
        <p><strong className="text-encre">L'équipe.</strong> {m.l_equipe}</p>
        {m.pour_le_cio?.length > 0 && (
          <Liste titre="Pour le CIO">
            <ul className="list-disc pl-5">{m.pour_le_cio.map((p: string, i: number) => <li key={i} className="mt-1">{p}</li>)}</ul>
          </Liste>
        )}
        {m.ecarts_constates?.length > 0 && (
          <Liste titre="Écarts constatés">
            <ul className="list-disc pl-5">{m.ecarts_constates.map((p: string, i: number) => <li key={i} className="mt-1">{p}</li>)}</ul>
          </Liste>
        )}
      </div>
    )
  if (f.tache === 'postmortem' || f.tache === 'revue')
    return (
      <>
        {m.bilan_par_membre?.length > 0 && (
          <Liste titre="Bilan par membre">
            <ul className="flex flex-col gap-3">
              {m.bilan_par_membre.map((b: any) => (
                <li key={b.membre} className="text-[14px]">
                  <p className="flex flex-wrap items-center gap-2 font-semibold text-encre">{b.membre} <Pastille ton={TON_STATUT[b.qualite]}>{b.qualite}</Pastille></p>
                  <p className="text-encre-2">{b.ce_qu_il_a_fait} {b.a_ameliorer && <span className="text-encre-3">À améliorer : {b.a_ameliorer}</span>}</p>
                </li>
              ))}
            </ul>
          </Liste>
        )}
        {(m.incidents ?? m.constats)?.length > 0 && (
          <Liste titre={f.tache === 'revue' ? 'Constats' : 'Incidents'}>
            <ul className="flex flex-col gap-3">
              {(m.incidents ?? m.constats).map((x: any, i: number) => (
                <li key={i} className="text-[14px]">
                  <p className="flex flex-wrap items-center gap-2"><Pastille ton={TON_STATUT[x.nature]}>{x.nature}</Pastille>
                    <span className="font-semibold text-encre">{x.quoi}</span></p>
                  <p className="mt-0.5 text-encre-2">{x.cause_probable}</p>
                </li>
              ))}
            </ul>
          </Liste>
        )}
        {m.memo_au_cio && <Liste titre="Mémo au CIO"><Texte>{m.memo_au_cio}</Texte></Liste>}
      </>
    )
  return null
}

export function Memo({ f, ouvert = false }: { f: MemoFichier; ouvert?: boolean }) {
  const [detail, setDetail] = useState(ouvert)
  return (
    <article className="carte p-5 md:p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-[13px] font-semibold text-encre-3">{nomTache(f.tache)}</p>
        <p className="chiffres text-[12.5px] text-encre-3">
          {jour(f.horodatage)}, {heureParis(f.horodatage)} · {f.cout_usd < 0.01 ? cents(f.cout_usd) : dollars(f.cout_usd)}
        </p>
      </header>
      {f.ok && f.memo ? (
        <>
          <h3 className="titre mt-2 text-[19px] font-semibold leading-snug text-encre">{f.memo.recap_court}</h3>
          <div className="mt-4"><Structure f={f} /></div>
          {f.memo.recap_detail && (
            <div className="mt-5 border-t border-ligne pt-4">
              <button onClick={() => setDetail(!detail)} aria-expanded={detail}
                className="inline-flex items-center gap-1.5 text-[14px] font-semibold text-accent">
                Compte rendu complet <CaretDown size={14} weight="bold" className={`transition-transform ${detail ? 'rotate-180' : ''}`} />
              </button>
              {detail && <div className="mt-3"><Texte>{f.memo.recap_detail}</Texte></div>}
            </div>
          )}
        </>
      ) : (
        <p className="mt-2 text-[15px] text-encre-2"><strong className="text-attention">Échec.</strong> {f.erreur}</p>
      )}
    </article>
  )
}
