/* Le protocole : où en sont les critères de la phase 2, la calibration du Research Analyst, et ce que coûte l'équipe. */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { useProtocole } from '../api'
import { Carte, EnTete, Erreur, Squelette, Vide } from '../composants/base'
import { cents, dollars, nombre, signe } from '../format'

const MEMBRES = ['Research Analyst', 'Risk Manager', 'Middle Office', 'Audit']
const TEINTES = ['var(--accent)', 'var(--nuit)', 'var(--encre-3)', 'color-mix(in srgb, var(--accent) 45%, var(--surface-3))']

function Critere({ code, titre, valeur, note }: { code: string; titre: string; valeur: React.ReactNode; note?: string | null }) {
  return (
    <div className="carte flex flex-col p-5">
      <p className="chiffres text-[13px] font-semibold text-accent">{code}</p>
      <p className="mt-1 text-[14px] text-encre-2">{titre}</p>
      <p className="chiffres titre mt-3 text-[30px] font-semibold leading-none text-encre">{valeur}</p>
      {note && <p className="mt-3 text-[13px] leading-snug text-encre-3">{note}</p>}
    </div>
  )
}

export default function Protocole() {
  const { data, error, isLoading } = useProtocole()
  if (error) return <Erreur erreur={error} />
  if (isLoading || !data) return <div className="grid gap-5"><Squelette className="h-10 w-72" /><Squelette className="h-40" /></div>
  const c = data.criteres
  const calibration = data.calibration.map((l) => ({
    jour: l.jour, gravite: Number(l.gravite), mouvement: Math.abs(Number(l.sp500_pct)), sp500: Number(l.sp500_pct), vix: Number(l.vix_points),
  }))
  const couts = data.couts_par_jour.map((j) => ({ jour: j.jour.slice(5).split('-').reverse().join('/'), ...j.par_membre_usd, total: j.total_usd }))

  return (
    <>
      <EnTete titre="Le protocole"
        sous="Les critères de la phase 2, tels que le code les mesure. Trois mois d'observation, jugés sur la fidélité au test et sur la performance." />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Critere code="F1" titre="Incidents critiques" valeur={c.F1_incidents_critiques} note="Zéro limite violée, zéro ordre imprévu." />
        <Critere code="F2" titre="Écarts avec le courtier" valeur={c.F2_ecarts_avec_le_courtier} note="Registre et IBKR doivent concorder." />
        <Critere code="F3 · F4" titre="Barreaux fermés" valeur={c.F3_F4_barreaux_fermes} note={c.F3_F4_note ?? 'Frais réels et écart à la simulation, par barreau.'} />
        <Critere code="P1" titre="Résultat depuis la référence" valeur={c.P1_resultat_usd == null ? '-' : signe(c.P1_resultat_usd)} note={c.P1_note} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Carte className="p-6">
          <p className="titre text-[19px] font-semibold">Calibration du Research Analyst</p>
          <p className="mt-1 text-[13px] text-encre-2">Gravité annoncée le matin, contre l'ampleur du mouvement du S&P 500 le soir. Calculée par le code, briefings tardifs exclus.</p>
          {calibration.length === 0 ? (
            <div className="mt-5"><Vide titre="Pas encore de journée complète">Il faut un briefing à l'heure et la clôture publiée par le CBOE, le soir même.</Vide></div>
          ) : (
            <div className="mt-4 h-[240px]">
              <ResponsiveContainer>
                <ScatterChart margin={{ left: 0, right: 12, top: 8 }}>
                  <CartesianGrid stroke="var(--ligne)" />
                  <XAxis type="number" dataKey="gravite" domain={[0.5, 5.5]} ticks={[1, 2, 3, 4, 5]} name="Gravité"
                    tick={{ fill: 'var(--encre-3)', fontSize: 12 }} tickLine={false} axisLine={false} />
                  <YAxis type="number" dataKey="mouvement" name="Mouvement" unit=" %" width={52}
                    tick={{ fill: 'var(--encre-3)', fontSize: 12 }} tickLine={false} axisLine={false} />
                  <ZAxis range={[90, 90]} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--ligne)', borderRadius: 10 }}
                    formatter={(v, n) => [n === 'Mouvement' ? `${nombre(Number(v))} %` : String(v), String(n)]} />
                  <Scatter data={calibration} fill="var(--accent)" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}
        </Carte>
        <Carte className="p-6">
          <p className="titre text-[19px] font-semibold">Coût de l'équipe</p>
          <p className="mt-1 text-[13px] text-encre-2">Par jour et par membre, chaque appel compté au centime.</p>
          {couts.length === 0 ? <div className="mt-5"><Vide titre="Aucun appel encore" /></div> : (
            <>
              <div className="mt-4 h-[200px]">
                <ResponsiveContainer>
                  <BarChart data={couts} margin={{ left: 0, right: 8, top: 8 }}>
                    <CartesianGrid stroke="var(--ligne)" vertical={false} />
                    <XAxis dataKey="jour" tick={{ fill: 'var(--encre-3)', fontSize: 12 }} tickLine={false} axisLine={false} />
                    <YAxis width={48} tick={{ fill: 'var(--encre-3)', fontSize: 12 }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v} $`} />
                    <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--ligne)', borderRadius: 10 }}
                      formatter={(v) => cents(Number(v))} cursor={{ fill: 'var(--accent-doux)' }} />
                    {MEMBRES.map((m, i) => <Bar key={m} dataKey={m} stackId="c" fill={TEINTES[i]} radius={i === MEMBRES.length - 1 ? [4, 4, 0, 0] : 0} />)}
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-encre-2">
                {MEMBRES.map((m, i) => (
                  <li key={m} className="flex items-center gap-2"><span className="size-2.5 rounded-[3px]" style={{ background: TEINTES[i] }} />{m}</li>
                ))}
              </ul>
            </>
          )}
        </Carte>
      </div>

      <Carte className="mt-6 overflow-x-auto p-6">
        <p className="titre text-[19px] font-semibold">Séances relevées</p>
        {data.seances.length === 0 ? (
          <div className="mt-4"><Vide titre="Aucune séance relevée">Le relevé chiffré commence à la prochaine séance du desk.</Vide></div>
        ) : (
          <table className="chiffres mt-4 w-full min-w-[560px] text-[14px]">
            <thead><tr className="text-left text-encre-3">
              {['Jour', 'Séance', 'Mode', 'Valeur', 'Barreaux', 'MES', 'Exposition'].map((h) => <th key={h} className="pb-2 font-semibold">{h}</th>)}
            </tr></thead>
            <tbody>
              {[...data.seances].reverse().slice(0, 12).map((s) => (
                <tr key={s.jour + s.moment} className="border-t border-ligne text-encre-2">
                  <td className="py-2">{s.jour.slice(8)}/{s.jour.slice(5, 7)}</td><td>{s.moment}</td><td>{s.mode}</td>
                  <td className="text-encre">{dollars(Number(s.valeur_liquidative))}</td><td>{s.barreaux}</td><td>{s.mes}</td><td>{s.delta_avant_couverture}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Carte>
    </>
  )
}
