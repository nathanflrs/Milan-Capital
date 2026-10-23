/* Les deux autres pods du desk hybride : le prop trader et l'acheteur de volatilité. */
import type { Pods as DonneesPods } from '../api'
import { Carte, Pastille, Vide } from './base'
import { dollars, echeance, nombre, signe } from '../format'

const dateCourte = (j: string) => `${j.slice(8, 10)}/${j.slice(5, 7)}`
const MOTIFS: Record<string, string> = { stop: 'Stop', objectif: 'Objectif', sortie: 'Sortie' }

function Mode({ mode }: { mode: string }) {
  return <Pastille ton={mode === 'reel' ? 'accent' : 'neutre'}>{mode === 'reel' ? 'Réel · paper' : 'Simulation'}</Pastille>
}

function Mesure({ libelle, valeur, ton }: { libelle: string; valeur: string; ton?: 'gain' | 'perte' }) {
  return (
    <div>
      <p className="text-[12.5px] text-encre-3">{libelle}</p>
      <p className={`chiffres mt-0.5 text-[17px] font-semibold ${ton === 'gain' ? 'text-accent' : ton === 'perte' ? 'text-perte' : ''}`}>{valeur}</p>
    </div>
  )
}

const ton = (x: number) => (x > 0 ? 'gain' : x < 0 ? 'perte' : undefined)

function Prop({ p }: { p: DonneesPods['prop'] }) {
  return (
    <Carte className="min-w-0 p-6 md:p-8">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="titre text-[19px] font-semibold">Prop trader</p>
          <p className="mt-1 text-[13px] text-encre-2">Actions du S&P 500, achat et vente à découvert. Stop posé chez le courtier.</p>
        </div>
        <div className="flex gap-2">{p.en_pause && <Pastille ton="attention">Pause du jour</Pastille>}<Mode mode={p.mode} /></div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Mesure libelle="Positions" valeur={`${p.positions.length} / 8`} />
        <Mesure libelle="Trades fermés" valeur={nombre(p.nombre_trades)} />
        <Mesure libelle="Résultat réalisé" valeur={signe(p.resultat_realise_usd)} ton={ton(p.resultat_realise_usd)} />
        <Mesure libelle="En R · réussite" valeur={p.nombre_trades ? `${signe(p.r_cumule, (n) => `${nombre(n)} R`)} · ${p.taux_reussite_pct} %` : '-'} />
      </div>
      {p.positions.length ? (
        <div className="mt-6 overflow-x-auto">
          <table className="chiffres w-full min-w-[520px] text-left text-[13.5px]">
            <thead className="text-[12px] text-encre-3">
              <tr><th className="pb-2 font-normal">Titre</th><th className="pb-2 font-normal">Sens</th><th className="pb-2 font-normal">Quantité</th>
                <th className="pb-2 font-normal">Entrée</th><th className="pb-2 font-normal">Stop</th><th className="pb-2 font-normal">Objectif</th><th className="pb-2 font-normal">Risque</th></tr>
            </thead>
            <tbody>
              {p.positions.map((x) => (
                <tr key={x.id} className="border-t border-ligne" title={x.catalyseur}>
                  <td className="py-2 font-semibold">{x.ticker}</td>
                  <td className="py-2">{x.sens > 0 ? 'Achat' : 'Vente'}</td>
                  <td className="py-2">{nombre(x.quantite)}</td>
                  <td className="py-2">{nombre(x.entree)}</td>
                  <td className="py-2">{nombre(x.stop)}</td>
                  <td className="py-2">{nombre(x.objectif)}</td>
                  <td className="py-2">{dollars(x.risque_initial_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-6"><Vide titre="Aucune position ouverte">Le Prop Trader lit le marché à 9 h 45 et 12 h 30, heure de New York. Le code vérifie chaque trade, le Risk Manager le relit.</Vide></div>
      )}
      {p.trades.length > 0 && (
        <div className="mt-6">
          <p className="text-[13px] font-semibold text-encre-2">Derniers trades</p>
          <ul className="mt-2 divide-y divide-ligne">
            {p.trades.slice(0, 6).map((t, i) => (
              <li key={`${t.ticker}-${t.ferme_le}-${i}`} className="chiffres flex items-center justify-between gap-3 py-2 text-[13.5px]">
                <span><span className="font-semibold">{t.ticker}</span> <span className="text-encre-3">{t.sens > 0 ? 'achat' : 'vente'} · {MOTIFS[t.motif] ?? t.motif} le {dateCourte(t.ferme_le)}</span></span>
                <span className={t.resultat_usd >= 0 ? 'text-accent' : 'text-perte'}>{signe(t.resultat_usd)} · {signe(t.r, (n) => `${nombre(n)} R`)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Carte>
  )
}

function Acheteur({ a }: { a: DonneesPods['acheteur'] }) {
  return (
    <Carte className="min-w-0 p-6">
      <div className="flex items-baseline justify-between gap-3">
        <p className="titre text-[19px] font-semibold">Acheteur de volatilité</p>
        <Mode mode={a.mode} />
      </div>
      <p className="mt-1 text-[13px] text-encre-2">Un straddle avant les résultats, quand les options sous-estiment le mouvement habituel.</p>
      <div className="mt-5 grid grid-cols-2 gap-4">
        <Mesure libelle="Prime engagée" valeur={`${dollars(a.prime_engagee_usd)}`} />
        <Mesure libelle={`Résultat · ${a.nombre_fermes} fermé${a.nombre_fermes > 1 ? 's' : ''}`} valeur={signe(a.resultat_usd)} ton={ton(a.resultat_usd)} />
      </div>
      <ul className="mt-5 divide-y divide-ligne">
        {a.straddles.map((s) => (
          <li key={s.ticker + s.echeance} className="chiffres py-2 text-[13.5px]">
            <span className="font-semibold">{s.ticker}</span> {nombre(s.strike)} · {echeance(s.echeance)} · {s.lots} lot{s.lots > 1 ? 's' : ''}
            <span className="block text-[12.5px] text-encre-3">Prévu {nombre(s.prevu * 100)} % contre {nombre(s.habituel * 100)} % d'habitude · réaction le {dateCourte(s.reaction_le)}</span>
          </li>
        ))}
        {a.fermes.slice(0, 4).map((f, i) => (
          <li key={`${f.ticker}-${f.ferme_le}-${i}`} className="chiffres flex justify-between gap-3 py-2 text-[13.5px]">
            <span><span className="font-semibold">{f.ticker}</span> <span className="text-encre-3">bougé {nombre(f.realise * 100)} % (prévu {nombre(f.prevu * 100)} %)</span></span>
            <span className={f.vente >= f.prime ? 'text-accent' : 'text-perte'}>{signe((f.vente - f.prime) * 100 * f.lots)}</span>
          </li>
        ))}
      </ul>
      {!a.straddles.length && !a.fermes.length && (
        <p className="mt-2 text-[13.5px] leading-relaxed text-encre-2">Aucun straddle pour l'instant. Examen chaque jour à 15 h 30 (New York) des 50 plus grandes sociétés qui publient le soir même ou le lendemain matin.</p>
      )}
    </Carte>
  )
}

export function Pods({ pods }: { pods: DonneesPods }) {
  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-[1.7fr_1fr]">
      <Prop p={pods.prop} />
      <Acheteur a={pods.acheteur} />
    </div>
  )
}
