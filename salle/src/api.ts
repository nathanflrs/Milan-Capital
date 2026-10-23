/*
 * Les données de la salle : rien n'est calculé ici, tout vient de l'API
 * (src/dashboard/salle.py), qui lit les journaux écrits par le code du fonds.
 *
 * Mode démonstration (VITE_DEMO=1, développement seulement) : un instantané
 * des vraies données du serveur, src/demo.json, sans connexion.
 */
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export const DEMO = import.meta.env.VITE_DEMO === '1'

export type Statut = 'en_veille' | 'au_travail' | 'termine' | 'alerte' | 'echec'

export interface Tache { membre: string; tache: string; a: string }

export interface Barreau {
  echeance: string; aile_put: number; centre: number; aile_call: number; lots: number
  ouvert_le: string; credit: number; perte_max_lot: number; jours: number
}

export interface PositionProp {
  id: string; ticker: string; sens: number; quantite: number; entree: number; stop: number
  objectif: number; ouvert_le: string; risque_initial_usd: number; catalyseur: string
}
export interface TradeProp {
  ticker: string; sens: number; quantite: number; entree: number; sortie: number; ouvert_le: string
  ferme_le: string; motif: string; resultat_usd: number; r: number
}
export interface StraddleOuvert {
  ticker: string; echeance: string; strike: number; lots: number; prime: number; ouvert_le: string
  reaction_le: string; prevu: number; habituel: number
}
export interface StraddleFerme extends Omit<StraddleOuvert, 'reaction_le'> { vente: number; ferme_le: string; realise: number }
export interface Pods {
  prop: {
    mode: string; positions: PositionProp[]; trades: TradeProp[]; nombre_trades: number
    resultat_realise_usd: number; r_cumule: number; taux_reussite_pct: number | null; en_pause: boolean
    journees: { jour: string; resultat_du_jour: number }[]
  }
  acheteur: {
    mode: string; straddles: StraddleOuvert[]; fermes: StraddleFerme[]; nombre_fermes: number
    resultat_usd: number; prime_engagee_usd: number
  }
}

export interface Etat {
  maintenant: string
  mode: 'simulation' | 'reel'
  valeur: number | null
  source_valeur: 'seance' | 'releve_v1' | 'releve_v2' | null
  date_valeur: string | null
  reference: number | null
  resultat_depuis_reference: number | null
  resultat_du_jour: number | null
  plus_haut: number | null
  baisse_depuis_plus_haut_pct: number | null
  etat_charte: 'normal' | 'reduire' | 'arret' | null
  seuils_charte_pct: { reduire: number; arret: number }
  barreaux: Barreau[]
  mes: Record<string, number>
  cycles_fermes: number
  derniere_seance: Record<string, string> | null
  xsp: number | null
  courbe_de_gain: { cours: number; gain_usd: number }[]
  historique: { points: { jour: string; valeur: number; epoque: 'v1' | 'v2'; resultat_depuis_debut: number }[]; debut_v2: string }
  prochaines_taches: Tache[]
  pods?: Pods
  couts: { periode_usd: number; par_membre_usd: Record<string, number>; mois_en_cours_usd: number; appels: number; echecs: number }
}

export interface Evenement {
  heure_utc: string; type: 'desk' | 'equipe'; gravite: 'info' | 'warning' | 'critical'
  qui: string; message: string; tache?: string | null; phase?: 'debut' | 'fin' | null
  ok?: boolean | null; cout_usd?: number | null; mode?: string | null
}

export interface Membre {
  titre: string; slug: string; nature: 'humain' | 'code' | 'claude'; modele: string | null
  mission: string; statut: Statut; derniere_action: Evenement | null; actions_du_jour: number
  prochaine_tache: Tache | null; cout_du_jour_usd: number
}

export interface MemoFichier {
  membre: string; tache: string; horodatage: string; ok: boolean; erreur: string | null
  cout_usd: number; tours: number; memo: Record<string, any> | null
}

export interface Historique { titre: string; memos: MemoFichier[]; carnet: string | null }

export interface Proposition {
  id: string; date: string; source: string; statut: 'en_attente' | 'validee' | 'rejetee'
  membre: string; lecon: string; justification: string; change_une_regle: boolean
  test_automatique: string; decision_le?: string; raison_cio?: string
}

export interface Protocole {
  criteres: Record<string, any>
  calibration: { jour: string; gravite: string; alerte: string; sp500_pct: string; vix_points: string }[]
  couts_par_jour: { jour: string; par_membre_usd: Record<string, number>; total_usd: number }[]
  seances: Record<string, string>[]
}

export class NonConnecte extends Error {}

let demoCache: any = null
async function demo() {
  if (!demoCache) demoCache = (await import('./demo.json')).default
  return demoCache
}

async function lire<T>(chemin: string): Promise<T> {
  if (DEMO) {
    const d = await demo()
    const table: Record<string, any> = {
      '/api/salle/etat': d.etat, '/api/salle/equipe': d.equipe, '/api/salle/fil': d.fil,
      '/api/salle/rapports': d.rapports, '/api/salle/protocole': d.protocole,
      '/api/salle/propositions': d.propositions, '/api/session': { authenticated: true, username: 'nathan' },
    }
    const membre = chemin.match(/^\/api\/salle\/equipe\/(.+)$/)
    if (membre) return (d.membres[membre[1]] ?? { titre: membre[1], memos: [], carnet: null }) as T
    return table[chemin.split('?')[0]] as T
  }
  const r = await fetch(chemin, { credentials: 'same-origin' })
  if (r.status === 401) throw new NonConnecte()
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

export const client = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, e) => !(e instanceof NonConnecte) && n < 2,
      refetchOnWindowFocus: true,
      staleTime: 15_000,
    },
  },
})

export const useSession = () =>
  useQuery({ queryKey: ['session'], queryFn: () => lire<{ authenticated: boolean; username: string | null }>('/api/session') })
export const useEtat = () => useQuery({ queryKey: ['etat'], queryFn: () => lire<Etat>('/api/salle/etat'), refetchInterval: 60_000 })
export const useEquipe = () => useQuery({ queryKey: ['equipe'], queryFn: () => lire<Membre[]>('/api/salle/equipe'), refetchInterval: 60_000 })
export const useFil = (jours = 2) => useQuery({ queryKey: ['fil', jours], queryFn: () => lire<Evenement[]>(`/api/salle/fil?jours=${jours}`) })
export const useRapports = () => useQuery({ queryKey: ['rapports'], queryFn: () => lire<MemoFichier[]>('/api/salle/rapports') })
export const useProtocole = () => useQuery({ queryKey: ['protocole'], queryFn: () => lire<Protocole>('/api/salle/protocole') })
export const usePropositions = () => useQuery({ queryKey: ['propositions'], queryFn: () => lire<Proposition[]>('/api/salle/propositions') })
export const useHistorique = (slug: string) =>
  useQuery({ queryKey: ['membre', slug], queryFn: () => lire<Historique>(`/api/salle/equipe/${slug}`) })

export async function connecter(username: string, password: string) {
  const r = await fetch('/api/login', {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(d.error || 'Connexion impossible.')
  return d
}

export async function deconnecter() {
  await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' })
}

export function useDecision() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, valider, raison }: { id: string; valider: boolean; raison: string }) => {
      if (DEMO) return { id, statut: valider ? 'validee' : 'rejetee' }
      const r = await fetch(`/api/salle/propositions/${encodeURIComponent(id)}/decision`, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ valider, raison }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d.detail || 'Décision non enregistrée.')
      return d
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['propositions'] })
      qc.invalidateQueries({ queryKey: ['membre'] })
    },
  })
}
