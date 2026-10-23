/* La salle des marchés : connexion, cadre, sections, et le lien profond des notifications (/?membre=…). */
import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { client, useEtat, useSession } from './api'
import { useDirect } from './live'
import { Cadre } from './composants/cadre'
import { Squelette } from './composants/base'
import Connexion from './pages/Connexion'
import Desk from './pages/Desk'

const Equipe = lazy(() => import('./pages/Equipe'))
const Membre = lazy(() => import('./pages/Membre'))
const Fil = lazy(() => import('./pages/Fil'))
const Rapports = lazy(() => import('./pages/Rapports'))
const Protocole = lazy(() => import('./pages/Protocole'))

function LienDeNotification() {
  const { search } = useLocation()
  const aller = useNavigate()
  useEffect(() => {
    const membre = new URLSearchParams(search).get('membre')
    if (membre) aller(`/equipe/${membre}`, { replace: true })
  }, [search, aller])
  return null
}

function Salle() {
  const direct = useDirect()
  const { data: etat } = useEtat()
  return (
    <Cadre direct={direct} mode={etat?.mode}>
      <LienDeNotification />
      <Suspense fallback={<Squelette className="h-40 w-full" />}>
        <Routes>
          <Route path="/" element={<Desk />} />
          <Route path="/equipe" element={<Equipe />} />
          <Route path="/equipe/:slug" element={<Membre />} />
          <Route path="/fil" element={<Fil />} />
          <Route path="/rapports" element={<Rapports />} />
          <Route path="/protocole" element={<Protocole />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Cadre>
  )
}

function Porte() {
  const qc = useQueryClient()
  const { data, isLoading } = useSession()
  if (isLoading) return <div className="min-h-[100dvh] bg-page" />
  if (!data?.authenticated) return <Connexion connecte={() => qc.invalidateQueries()} />
  return <Salle />
}

export default function App() {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Porte />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
