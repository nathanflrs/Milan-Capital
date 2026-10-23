/* Les pièces de base de la salle : logo, voyants, cartes, états vides et de chargement. */
import Markdown from 'react-markdown'
import type { ReactNode } from 'react'
import type { Statut } from '../api'

export const ARCADE =
  'M0 0H390V24H388Q382 24 382 30V206Q382 214 390 216V228H326V218Q332 216 332 208V85A55 55 0 0 0 222 85V208Q222 216 228 218V228H162V218Q168 216 168 208V85A55 55 0 0 0 58 85V208Q58 216 64 218V228H0V216Q8 214 8 206V30Q8 24 2 24H0Z'

export function Arcade({ className = 'h-6', titre = 'Milan Capital' }: { className?: string; titre?: string }) {
  return (
    <svg viewBox="0 0 390 228" className={className} role="img" aria-label={titre}>
      <path fill="currentColor" d={ARCADE} />
    </svg>
  )
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-3 whitespace-nowrap text-encre">
      <Arcade className="h-[20px] w-auto md:h-[22px]" />
      {!compact && <span className="titre text-[19px] font-semibold leading-none md:text-[21px]">Milan Capital</span>}
    </span>
  )
}

const LIBELLES: Record<Statut, string> = {
  en_veille: 'En veille', au_travail: 'Au travail', termine: 'Terminé', alerte: 'Alerte', echec: 'Échec',
}

export function Voyant({ statut, avecTexte = true }: { statut: Statut; avecTexte?: boolean }) {
  const pastille = {
    en_veille: 'border border-ligne-forte bg-transparent',
    au_travail: 'bg-accent voyant-travail',
    termine: 'bg-encre-3',
    alerte: 'bg-alerte',
    echec: 'bg-attention',
  }[statut]
  return (
    <span className="inline-flex items-center gap-2 text-[13px] text-encre-2" role="status">
      <span className={`inline-block size-2 rounded-full ${pastille}`} aria-hidden />
      {avecTexte && LIBELLES[statut]}
    </span>
  )
}

export function Carte({ children, className = '', as: Tag = 'section' }:
  { children: ReactNode; className?: string; as?: any }) {
  return <Tag className={`carte ${className}`}>{children}</Tag>
}

export function EnTete({ titre, sous, action }: { titre: string; sous?: ReactNode; action?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4 md:mb-8">
      <div>
        <h1 className="titre text-[28px] font-semibold leading-tight md:text-[34px]">{titre}</h1>
        {sous && <p className="mt-1.5 max-w-[62ch] text-[15px] text-encre-2">{sous}</p>}
      </div>
      {action}
    </header>
  )
}

export function Vide({ titre, children }: { titre: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-[14px] border border-dashed border-ligne-forte p-6">
      <Arcade className="h-4 w-auto text-encre-3" titre="" />
      <p className="titre text-[17px] font-semibold text-encre">{titre}</p>
      {children && <p className="max-w-[56ch] text-[14px] leading-relaxed text-encre-2">{children}</p>}
    </div>
  )
}

export function Squelette({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`squelette ${className}`} aria-hidden />
}

export function Erreur({ erreur }: { erreur: unknown }) {
  return (
    <div className="rounded-[14px] border border-ligne-forte p-5 text-[14px] text-encre-2" role="alert">
      <p className="font-semibold text-encre">Données indisponibles pour le moment.</p>
      <p className="mt-1">Le serveur ne répond pas ({String((erreur as Error)?.message ?? erreur)}). Nouvel essai automatique.</p>
    </div>
  )
}

export function Texte({ children }: { children?: string | null }) {
  if (!children) return null
  return <div className="prose-memo"><Markdown>{children}</Markdown></div>
}

export function Pastille({ children, ton = 'neutre' }: { children: ReactNode; ton?: 'neutre' | 'accent' | 'alerte' | 'attention' }) {
  const t = {
    neutre: 'bg-surface-2 text-encre-2',
    accent: 'bg-accent-doux text-accent',
    alerte: 'bg-[color-mix(in_srgb,var(--alerte)_12%,transparent)] text-alerte',
    attention: 'bg-[color-mix(in_srgb,var(--attention)_14%,transparent)] text-attention',
  }[ton]
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${t}`}>{children}</span>
}

export function Chiffre({ libelle, valeur, detail, grand = false }:
  { libelle: string; valeur: ReactNode; detail?: ReactNode; grand?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[13px] text-encre-3">{libelle}</p>
      <p className={`chiffres mt-1 font-semibold text-encre ${grand ? 'titre text-[40px] leading-none md:text-[52px]' : 'text-[22px] leading-tight'}`}>
        {valeur}
      </p>
      {detail && <p className="chiffres mt-1.5 text-[13px] text-encre-2">{detail}</p>}
    </div>
  )
}
