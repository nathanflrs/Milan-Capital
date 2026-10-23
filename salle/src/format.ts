/* Formats français : montants, pourcentages, heures (Paris et New York). */

const USD = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'USD', currencyDisplay: 'narrowSymbol', maximumFractionDigits: 0 })
const USD_CENTS = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'USD', currencyDisplay: 'narrowSymbol', minimumFractionDigits: 2, maximumFractionDigits: 2 })
const NOMBRE = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 })

export const dollars = (x: number | null | undefined) => (x == null ? '-' : USD.format(x))
export const cents = (x: number | null | undefined) => (x == null ? '-' : USD_CENTS.format(x))
export const nombre = (x: number | null | undefined) => (x == null ? '-' : NOMBRE.format(x))

export function signe(x: number | null | undefined, f: (n: number) => string = dollars) {
  if (x == null) return '-'
  return `${x > 0 ? '+' : x < 0 ? '−' : ''}${f(Math.abs(x))}`
}

export const pct = (x: number | null | undefined, decimales = 1) =>
  x == null ? '-' : `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x).toLocaleString('fr-FR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })} %`

const HEURE = (tz: string) => new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit', timeZone: tz })
const JOUR_HEURE = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris' })
const JOUR = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Europe/Paris' })

export const iso = (s: string) => new Date(s.endsWith('Z') || /[+-]\d\d:\d\d$/.test(s) ? s : `${s}Z`)
export const heureParis = (s: string) => HEURE('Europe/Paris').format(iso(s))
export const heureNY = (s: string) => HEURE('America/New_York').format(iso(s))
export const jourHeure = (s: string) => JOUR_HEURE.format(iso(s))
export const jour = (s: string) => JOUR.format(iso(s))

export function ilYa(s: string, maintenant = Date.now()) {
  const m = Math.round((maintenant - iso(s).getTime()) / 60000)
  if (m < 1) return "à l'instant"
  if (m < 60) return `il y a ${m} min`
  const h = Math.round(m / 60)
  if (h < 24) return `il y a ${h} h`
  return `il y a ${Math.round(h / 24)} j`
}

export function dans(s: string, maintenant = Date.now()) {
  const m = Math.round((iso(s).getTime() - maintenant) / 60000)
  if (m < 1) return 'maintenant'
  if (m < 60) return `dans ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `dans ${h} h ${String(m % 60).padStart(2, '0')}`
  return jourHeure(s)
}

export const echeance = (e: string) =>
  new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' })
    .format(new Date(`${e.slice(0, 4)}-${e.slice(4, 6)}-${e.slice(6, 8)}T12:00:00Z`))

export const TACHES: Record<string, string> = {
  briefing: 'Briefing du matin', veille: 'Veille', tri: 'Tri de la veille', analyse: 'Analyse',
  relecture: 'Relecture', rapport: 'Rapport du soir', postmortem: 'Post-mortem', revue: 'Revue de la semaine',
  decision: 'Décision', '10:30': 'Séance de 10 h 30', '15:30': 'Séance de 15 h 30',
  ouverture: 'Ouverture', suivi: 'Suivi de mi-séance', cloture: 'Clôture des comptes',
  entree: 'Achats d’avant résultats', sortie: 'Reventes', 'relecture-prop': 'Relecture du prop',
  'relecture prop': 'Relecture du prop',
}
export const nomTache = (t?: string | null) => (t ? TACHES[t] ?? t : '')
