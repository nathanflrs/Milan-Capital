/* Le cadre de la salle : navigation (barre latérale sur ordinateur, onglets sur téléphone), thème, notifications, direct. */
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Bank, Bell, BellSlash, ChartLineUp, Moon, Newspaper, Scroll, SignOut, Sun, UsersThree } from '@phosphor-icons/react'
import { DEMO, deconnecter } from '../api'
import type { EtatDirect } from '../live'
import { Logo } from './base'

const SECTIONS = [
  { a: '/', libelle: 'Le desk', court: 'Desk', icone: Bank, fin: true },
  { a: '/equipe', libelle: "L'équipe", court: 'Équipe', icone: UsersThree },
  { a: '/fil', libelle: 'Le fil', court: 'Fil', icone: Newspaper },
  { a: '/rapports', libelle: 'Rapports', court: 'Rapports', icone: Scroll },
  { a: '/protocole', libelle: 'Le protocole', court: 'Protocole', icone: ChartLineUp },
]

type Theme = 'clair' | 'sombre'

function lireTheme(): Theme {
  try {
    const t = localStorage.getItem('milan-theme')
    if (t === 'clair' || t === 'sombre') return t
  } catch { /* stockage indisponible */ }
  // Choix de Nathan : la salle s'ouvre en clair ; le sombre reste à un bouton.
  return 'clair'
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(lireTheme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme === 'sombre' ? 'dark' : 'light'
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'sombre' ? '#0a1220' : '#f2f4f8')
  }, [theme])
  const basculer = () => {
    const t = theme === 'sombre' ? 'clair' : 'sombre'
    try { localStorage.setItem('milan-theme', t) } catch { /* rien */ }
    setTheme(t)
  }
  return [theme, basculer]
}

function b64(base64: string) {
  const p = '='.repeat((4 - (base64.length % 4)) % 4)
  const raw = atob((base64 + p).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

type EtatNotif = 'inconnu' | 'actives' | 'inactives' | 'refusees' | 'impossibles'

// Un appui sur la cloche répond toujours : il inscrit l'appareil si besoin, puis
// envoie un test à CET appareil et dit ce qui s'est passé. Avant, une cloche
// déjà active ne faisait rien au toucher, et rien ne disait si ça marchait.
function useNotifications(): [EtatNotif, () => Promise<void>, string | null] {
  const [etat, setEtat] = useState<EtatNotif>('inconnu')
  const [message, setMessage] = useState<string | null>(null)
  const dire = (m: string) => { setMessage(m); setTimeout(() => setMessage(null), 7000) }
  const inscrire = (sub: PushSubscription) => fetch('/api/push/subscribe', {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(sub),
  })
  useEffect(() => {
    if (DEMO || !('serviceWorker' in navigator) || !('PushManager' in window)) { setEtat('impossibles'); return }
    if (Notification.permission === 'denied') { setEtat('refusees'); return }
    navigator.serviceWorker.register('/sw.js').then(async (reg) => {
      const s = await reg.pushManager.getSubscription()
      // Réinscrit l'appareil à chaque ouverture : le serveur le retrouve même
      // s'il l'avait oublié (inscription idempotente).
      if (s) inscrire(s).catch(() => {})
      setEtat(s ? 'actives' : 'inactives')
    }).catch(() => setEtat('impossibles'))
  }, [])
  const activer = async () => {
    if (etat === 'impossibles') {
      dire('Sur iPhone : ouvre la salle depuis son icône sur l’écran d’accueil (Partager → Sur l’écran d’accueil), puis touche la cloche.')
      return
    }
    if (etat === 'refusees') { dire('Notifications refusées : autorise-les dans Réglages → Notifications → Milan Capital.'); return }
    try {
      const reg = await navigator.serviceWorker.ready
      let sub = await reg.pushManager.getSubscription()
      if (!sub) {
        const permission = await Notification.requestPermission()
        if (permission !== 'granted') { setEtat('refusees'); dire('Notifications refusées sur cet appareil.'); return }
        const { public_key } = await (await fetch('/api/push/key', { credentials: 'same-origin' })).json()
        sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(public_key) })
      }
      await inscrire(sub)
      setEtat('actives')
      const r = await (await fetch('/api/push/test', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: sub.endpoint }),
      })).json()
      dire(r.ok ? 'Test envoyé à cet appareil : la notification arrive dans quelques secondes.'
        : `Le test n’est pas parti (${r.detail ?? 'erreur'}).`)
    } catch {
      dire('Impossible de joindre le serveur des notifications.')
    }
  }
  return [etat, activer, message]
}

function Direct({ etat }: { etat: EtatDirect }) {
  const texte = { connecte: 'En direct', reconnexion: 'Reconnexion…', demo: 'Démonstration' }[etat]
  return (
    <span className="inline-flex items-center gap-2 text-[12px] font-semibold text-encre-3" role="status">
      <span className={`size-1.5 rounded-full ${etat === 'connecte' ? 'bg-accent' : 'bg-encre-3'}`} aria-hidden />
      <span className="max-sm:sr-only">{texte}</span>
    </span>
  )
}

export function Cadre({ children, direct, mode }: { children: ReactNode; direct: EtatDirect; mode?: string }) {
  const [theme, basculer] = useTheme()
  const [notif, activer, messageNotif] = useNotifications()
  const sortir = async () => { await deconnecter(); location.reload() }

  return (
    <div className="min-h-[100dvh] bg-page md:grid md:grid-cols-[248px_1fr]">
      {/* Barre latérale, ordinateur */}
      <aside className="sticky top-0 hidden h-[100dvh] flex-col border-r border-ligne bg-surface px-5 py-6 md:flex">
        <Logo />
        <p className="etiquette mt-3">Salle des marchés</p>
        <nav className="mt-9 flex flex-col gap-1" aria-label="Sections">
          {SECTIONS.map(({ a, libelle, icone: Icone, fin }) => (
            <NavLink key={a} to={a} end={fin}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-[15px] transition-colors ${
                  isActive ? 'bg-accent-doux font-semibold text-encre' : 'text-encre-2 hover:bg-surface-2 hover:text-encre'}`}>
              {({ isActive }) => (<><Icone size={19} weight={isActive ? 'fill' : 'regular'} className={isActive ? 'text-accent' : ''} />{libelle}</>)}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-4 border-t border-ligne pt-5">
          {mode && (
            <div>
              <p className="text-[12px] text-encre-3">Mode du desk</p>
              <p className="mt-0.5 text-[14px] font-semibold text-encre">{mode === 'reel' ? 'Réel (paper IBKR)' : 'Simulation'}</p>
            </div>
          )}
          <Direct etat={direct} />
          <div className="flex items-center gap-1">
            <button onClick={basculer} className="rounded-[10px] p-2 text-encre-2 hover:bg-surface-2 hover:text-encre"
              aria-label={theme === 'sombre' ? 'Passer en mode clair' : 'Passer en mode sombre'}>
              {theme === 'sombre' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button onClick={activer}
              className="rounded-[10px] p-2 text-encre-2 hover:bg-surface-2 hover:text-encre"
              aria-label="Notifications sur cet appareil"
              title={{ actives: 'Notifications actives : toucher pour envoyer un test', inactives: 'Activer les notifications sur cet appareil',
                refusees: 'Notifications refusées dans les réglages', impossibles: 'Notifications indisponibles ici', inconnu: '' }[notif]}>
              {notif === 'actives' ? <Bell size={18} weight="fill" className="text-accent" /> : notif === 'inactives' ? <Bell size={18} /> : <BellSlash size={18} />}
            </button>
            {!DEMO && (
              <button onClick={sortir} className="ml-auto rounded-[10px] p-2 text-encre-2 hover:bg-surface-2 hover:text-encre" aria-label="Se déconnecter">
                <SignOut size={18} />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* En-tête, téléphone */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-ligne bg-surface/90 px-4 pb-3 pt-[max(12px,env(safe-area-inset-top))] backdrop-blur md:hidden">
        <Logo />
        <div className="flex items-center gap-1">
          <Direct etat={direct} />
          <button onClick={basculer} className="rounded-[10px] p-2 text-encre-2" aria-label="Changer de thème">
            {theme === 'sombre' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button onClick={activer} className="rounded-[10px] p-2 text-encre-2"
            aria-label={notif === 'actives' ? 'Envoyer une notification de test' : 'Activer les notifications'}>
            {notif === 'actives' ? <Bell size={18} weight="fill" className="text-accent" /> : notif === 'inactives' ? <Bell size={18} /> : <BellSlash size={18} />}
          </button>
        </div>
      </header>

      {messageNotif && (
        <p role="status" className="fixed inset-x-4 top-[max(68px,calc(env(safe-area-inset-top)+56px))] z-30 mx-auto max-w-md rounded-[12px] bg-[var(--nuit-panneau)] px-4 py-3 text-[14px] leading-snug text-[var(--nuit-panneau-encre)] shadow-[var(--ombre)] md:top-6">
          {messageNotif}
        </p>
      )}

      <main className="mx-auto w-full max-w-[1240px] px-4 pb-28 pt-6 md:px-10 md:pb-16 md:pt-10">{children}</main>

      {/* Onglets, téléphone */}
      <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-ligne bg-surface/95 pb-[max(8px,env(safe-area-inset-bottom))] pt-1.5 backdrop-blur md:hidden" aria-label="Sections">
        {SECTIONS.map(({ a, court, icone: Icone, fin }) => (
          <NavLink key={a} to={a} end={fin} className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 py-1 text-[10.5px] ${isActive ? 'font-semibold text-encre' : 'text-encre-3'}`}>
            {({ isActive }) => (<><Icone size={22} weight={isActive ? 'fill' : 'regular'} className={isActive ? 'text-accent' : ''} />{court}</>)}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
