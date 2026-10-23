/*
 * Le direct : le flux d'événements du serveur (/api/events/stream).
 *
 * Téléphone et Mac écoutent le même flux : à chaque événement du desk ou de
 * l'équipe, les données concernées sont relues, et les deux appareils
 * affichent la même chose à la seconde près.
 */
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { DEMO } from './api'

export type EtatDirect = 'connecte' | 'reconnexion' | 'demo'

export function useDirect(): EtatDirect {
  const qc = useQueryClient()
  const [etat, setEtat] = useState<EtatDirect>(DEMO ? 'demo' : 'reconnexion')

  useEffect(() => {
    if (DEMO) return
    let source: EventSource | null = null
    let attente: number | undefined
    let ferme = false

    const ouvrir = () => {
      source = new EventSource('/api/events/stream', { withCredentials: true })
      source.onopen = () => setEtat('connecte')
      source.onmessage = (m) => {
        try {
          const e = JSON.parse(m.data)
          if (e.type !== 'desk' && e.type !== 'equipe') return
        } catch {
          return
        }
        qc.invalidateQueries({ queryKey: ['equipe'] })
        qc.invalidateQueries({ queryKey: ['fil'] })
        qc.invalidateQueries({ queryKey: ['etat'] })
        qc.invalidateQueries({ queryKey: ['rapports'] })
        qc.invalidateQueries({ queryKey: ['propositions'] })
        qc.invalidateQueries({ queryKey: ['membre'] })
      }
      source.onerror = () => {
        setEtat('reconnexion')
        source?.close()
        if (!ferme) attente = window.setTimeout(ouvrir, 5000)
      }
    }
    ouvrir()
    return () => {
      ferme = true
      source?.close()
      window.clearTimeout(attente)
    }
  }, [qc])

  return etat
}
