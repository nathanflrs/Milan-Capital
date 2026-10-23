/* Le travail d'un membre : ses mémos des deux dernières semaines, et son carnet de leçons. */
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from '@phosphor-icons/react'
import { useEquipe, useHistorique } from '../api'
import { Carte, EnTete, Erreur, Squelette, Texte, Vide, Voyant } from '../composants/base'
import { Memo } from '../composants/memo'

export default function Membre() {
  const { slug = '' } = useParams()
  const { data, error, isLoading } = useHistorique(slug)
  const { data: equipe } = useEquipe()
  const membre = equipe?.find((m) => m.slug === slug)
  if (error) return <Erreur erreur={error} />
  return (
    <>
      <Link to="/equipe" className="mb-5 inline-flex items-center gap-1.5 text-[14px] font-semibold text-encre-2 hover:text-encre">
        <ArrowLeft size={15} weight="bold" /> L'équipe
      </Link>
      <EnTete titre={data?.titre ?? membre?.titre ?? '…'} sous={membre?.mission}
        action={membre && <Voyant statut={membre.statut} />} />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="flex flex-col gap-5">
          {isLoading || !data ? (
            <><Squelette className="h-48" /><Squelette className="h-48" /></>
          ) : data.memos.length ? (
            data.memos.map((f, i) => <Memo key={f.horodatage + f.tache} f={f} ouvert={i === 0} />)
          ) : (
            <Vide titre="Aucun mémo sur les deux dernières semaines">
              {membre?.nature === 'code'
                ? 'Ce membre est du code testé : son travail apparaît dans le fil, séance par séance.'
                : 'Les mémos de ce membre apparaîtront ici dès sa prochaine tâche.'}
            </Vide>
          )}
        </div>
        <aside>
          <Carte className="p-5 lg:sticky lg:top-8">
            <p className="titre text-[17px] font-semibold">Carnet de leçons</p>
            <p className="mt-1 text-[13px] text-encre-3">Leçons validées par le CIO, relues à chaque tâche.</p>
            <div className="mt-4">
              {data?.carnet ? <Texte>{data.carnet.replace(/^# .*\n/, '')}</Texte>
                : <p className="text-[14px] text-encre-2">Aucune leçon validée pour l'instant.</p>}
            </div>
          </Carte>
        </aside>
      </div>
    </>
  )
}
