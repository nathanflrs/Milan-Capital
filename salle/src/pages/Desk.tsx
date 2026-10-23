/* Le desk : l'état du fonds, la charte, la journée, l'échelle des barreaux. */
import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from '@phosphor-icons/react'
import { useEtat, type Barreau, type Etat } from '../api'
import { Carte, Chiffre, EnTete, Erreur, Pastille, Squelette, Vide } from '../composants/base'
import { cents, dans, dollars, echeance, heureNY, heureParis, jour, nombre, pct, signe } from '../format'

// Recharts est lourd : les graphiques arrivent après le reste de l'écran.
const CourbeValeur = lazy(() => import('../composants/graphiques').then((m) => ({ default: m.CourbeValeur })))
const CourbeGain = lazy(() => import('../composants/graphiques').then((m) => ({ default: m.CourbeGain })))

function Jauge({ etat }: { etat: Etat }) {
  const baisse = etat.baisse_depuis_plus_haut_pct
  const position = baisse == null ? 0 : Math.min(Math.abs(Math.min(baisse, 0)) / 15, 1) * 100
  const texte = { normal: 'Normal', reduire: 'Taille divisée par deux', arret: 'Desk à l’arrêt' }[etat.etat_charte ?? 'normal']
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-[13px] text-encre-3">Charte : baisse depuis le plus haut</p>
        <p className="chiffres text-[13px] font-semibold text-encre">{baisse == null ? 'Pas encore mesurée' : `${pct(baisse, 2)} · ${texte}`}</p>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-surface-2" role="img"
        aria-label={`Baisse ${baisse ?? 0} %, seuils à −8 % et −15 %`}>
        <div className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${Math.max(position, 1.5)}%` }} />
        <span className="absolute -top-1 h-4 w-px bg-encre-3" style={{ left: `${(8 / 15) * 100}%` }} />
        <span className="absolute -top-1 right-0 h-4 w-px bg-alerte" />
      </div>
      <div className="chiffres relative mt-2 h-4 text-[12px] text-encre-3">
        <span className="absolute left-0">0 %</span>
        <span className="absolute -translate-x-1/2" style={{ left: `${(8 / 15) * 100}%` }}>−8 % réduction</span>
        <span className="absolute right-0">−15 % arrêt</span>
      </div>
    </div>
  )
}

function Journee({ etat }: { etat: Etat }) {
  return (
    <section className="rounded-[16px] bg-[var(--nuit-panneau)] p-6 text-[var(--nuit-panneau-encre)] shadow-[var(--ombre)]">
      <p className="titre text-[19px] font-semibold">La suite de la journée</p>
      <p className="mt-1 text-[13px] text-white/60">Heure de Paris, et de New York entre parenthèses.</p>
      <ol className="mt-5 flex flex-col gap-4">
        {etat.prochaines_taches.slice(0, 5).map((t) => (
          <li key={`${t.membre}-${t.tache}`} className="grid grid-cols-[76px_1fr] gap-3">
            <div className="chiffres">
              <p className="text-[17px] font-semibold leading-tight">{heureParis(t.a)}</p>
              <p className="text-[12px] text-white/55">({heureNY(t.a)})</p>
            </div>
            <div className="min-w-0 border-l border-white/12 pl-3">
              <p className="text-[15px] font-semibold leading-tight">{t.membre}</p>
              <p className="text-[13px] text-white/65">{t.tache}, {dans(t.a)}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Echelle({ barreaux }: { barreaux: Barreau[] }) {
  if (!barreaux.length)
    return (
      <Vide titre="Aucun barreau ouvert">
        Le Volatility Trader propose le barreau de la semaine au contrôle de 10 h 30 à New York, le premier jour de
        bourse de la semaine. Le Risk Manager le relit avant tout ordre. En simulation, rien n'est transmis au marché.
      </Vide>
    )
  const horizon = Math.max(35, ...barreaux.map((b) => b.jours))
  return (
    <div className="flex flex-col gap-3">
      {barreaux.map((b) => {
        return (
          <div key={b.echeance + b.ouvert_le} className="grid grid-cols-[112px_1fr] items-center gap-4">
            <div>
              <p className="chiffres text-[15px] font-semibold">{echeance(b.echeance)}</p>
              <p className="chiffres text-[12px] text-encre-3">{b.aile_put} / {b.centre} / {b.aile_call}</p>
            </div>
            <div className="relative h-8 rounded-[8px] bg-surface-2">
              <div className="absolute inset-y-0 rounded-[8px] bg-accent-doux"
                style={{ left: 0, width: `${(b.jours / horizon) * 100}%` }} />
              <div className="absolute inset-y-1.5 w-px bg-encre-3" style={{ left: `${(Math.max(b.jours - 7, 0) / horizon) * 100}%` }}
                title="Sortie à 7 jours" />
              <p className="chiffres absolute inset-y-0 left-3 flex items-center text-[12.5px] text-encre-2">
                {b.jours} j restants · crédit {nombre(b.credit)} · {b.lots} lot{b.lots > 1 ? 's' : ''}
              </p>
            </div>
          </div>
        )
      })}
      <p className="text-[12px] text-encre-3">Le trait marque la sortie, 7 jours avant l'échéance.</p>
    </div>
  )
}

export default function Desk() {
  const { data: etat, error, isLoading } = useEtat()
  if (error) return <Erreur erreur={error} />
  if (isLoading || !etat)
    return (
      <div className="grid gap-6">
        <Squelette className="h-10 w-64" /><Squelette className="h-48 w-full" /><Squelette className="h-32 w-full" />
      </div>
    )

  const s = etat.derniere_seance
  return (
    <>
      <EnTete titre="Le desk"
        sous={<>{jour(etat.maintenant).replace(/^./, (c) => c.toUpperCase())}. Desk de volatilité sur XSP, couvert en micro-futures MES.</>}
        action={<Pastille ton={etat.mode === 'reel' ? 'accent' : 'neutre'}>{etat.mode === 'reel' ? 'Réel · paper IBKR' : 'Simulation · rien n’est transmis'}</Pastille>} />

      <div className="grid gap-6 lg:grid-cols-[1.7fr_1fr]">
        <Carte className="flex flex-col gap-8 p-6 md:p-8">
          {etat.valeur == null ? (
            <Vide titre="Pas encore de séance enregistrée">
              La valeur du fonds s'affiche ici dès la prochaine séance du desk, à partir du relevé chiffré qu'elle écrit.
            </Vide>
          ) : (
            <div className="grid gap-6 sm:grid-cols-[1.4fr_1fr_1fr]">
              <Chiffre grand libelle="Valeur du fonds" valeur={dollars(etat.valeur)}
                detail={etat.source_valeur === 'seance' ? `Plus haut ${dollars(etat.plus_haut)}`
                  : `Relevé du ${etat.date_valeur?.slice(8)}/${etat.date_valeur?.slice(5, 7)}, arène v1`} />
              <Chiffre libelle="Aujourd'hui" valeur={signe(etat.resultat_du_jour)}
                detail={etat.resultat_du_jour == null ? 'Après deux séances du jour' : 'Entre les deux séances'} />
              {etat.resultat_depuis_reference != null ? (
                <Chiffre libelle="Depuis la référence" valeur={signe(etat.resultat_depuis_reference)}
                  detail={etat.mode === 'reel' ? 'Depuis l’armement' : 'Depuis la première séance du desk'} />
              ) : (
                <Chiffre libelle="Depuis le 13 août" valeur={signe(etat.historique.points.at(-1)?.resultat_depuis_debut)}
                  detail="Premier relevé du serveur" />
              )}
            </div>
          )}
          <Jauge etat={etat} />
        </Carte>
        <Journee etat={etat} />
      </div>

      <div className="mt-6">
        <Suspense fallback={<Squelette className="h-[380px] w-full" />}><CourbeValeur etat={etat} /></Suspense>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.7fr_1fr]">
        <Carte className="p-6 md:p-8">
          <div className="mb-5 flex items-baseline justify-between gap-4">
            <p className="titre text-[19px] font-semibold">L'échelle des barreaux</p>
            <p className="text-[13px] text-encre-3">Un iron butterfly par semaine, ~30 jours</p>
          </div>
          <Echelle barreaux={etat.barreaux} />
        </Carte>
        <Carte className="p-6">
          <p className="titre text-[19px] font-semibold">Dernière séance</p>
          {s ? (
            <dl className="chiffres mt-4 grid grid-cols-2 gap-x-4 gap-y-4 text-[14px]">
              <div><dt className="text-encre-3">Séance</dt><dd className="font-semibold">{s.jour.slice(8)}/{s.jour.slice(5, 7)} · {s.moment}</dd></div>
              <div><dt className="text-encre-3">Barreaux</dt><dd className="font-semibold">{s.barreaux}</dd></div>
              <div><dt className="text-encre-3">MES</dt><dd className="font-semibold">{s.mes}</dd></div>
              <div><dt className="text-encre-3">Exposition</dt><dd className="font-semibold">{s.delta_avant_couverture} unités</dd></div>
              <div><dt className="text-encre-3">Barreaux fermés</dt><dd className="font-semibold">{etat.cycles_fermes}</dd></div>
              <div><dt className="text-encre-3">Équipe aujourd'hui</dt><dd className="font-semibold">{cents(etat.couts.periode_usd)}</dd></div>
            </dl>
          ) : (
            <p className="mt-3 text-[14px] leading-relaxed text-encre-2">
              Aucune séance relevée pour l'instant. Coût de l'équipe aujourd'hui : <span className="chiffres font-semibold text-encre">{cents(etat.couts.periode_usd)}</span>,
              {' '}<span className="chiffres font-semibold text-encre">{cents(etat.couts.mois_en_cours_usd)}</span> ce mois-ci.
            </p>
          )}
          <Link to="/equipe" className="mt-6 inline-flex items-center gap-1.5 text-[14px] font-semibold text-accent">
            Voir l'équipe au travail <ArrowRight size={15} weight="bold" />
          </Link>
        </Carte>
      </div>

      {etat.courbe_de_gain.length > 0 && (
        <div className="mt-6"><Suspense fallback={<Squelette className="h-[340px] w-full" />}><CourbeGain etat={etat} /></Suspense></div>
      )}
    </>
  )
}
