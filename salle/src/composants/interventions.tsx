/* Le bandeau qui rappelle, sur chaque écran, ce qui attend une réponse du CIO. */
import { Link, useLocation } from 'react-router-dom'
import { Warning } from '@phosphor-icons/react'
import { useInterventions } from '../api'

export function BandeauInterventions() {
  const { pathname } = useLocation()
  const { data } = useInterventions()
  const ouvertes = (data ?? []).filter((d) => d.statut === 'ouverte')
  if (!ouvertes.length || pathname.startsWith('/interventions')) return null
  const n = ouvertes.length
  return (
    <Link to="/interventions" className="mb-5 flex items-center gap-2.5 rounded-[10px] border border-alerte px-4 py-3 text-[14.5px] font-semibold text-alerte">
      <Warning size={19} weight="fill" aria-hidden />
      {n > 1 ? `${n} demandes attendent ta réponse` : '1 demande attend ta réponse'}
    </Link>
  )
}
