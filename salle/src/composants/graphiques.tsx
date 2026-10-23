/* Les graphiques du desk, chargés à la demande (Recharts est lourd). */
import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Etat } from '../api'
import { dollars, nombre, signe } from '../format'

const AXE = { fill: 'var(--encre-3)', fontSize: 12 }
const BULLE = { background: 'var(--surface)', border: '1px solid var(--ligne)', borderRadius: 10, fontSize: 13 }
const dateCourte = (j: string) => `${j.slice(8, 10)}/${j.slice(5, 7)}`
const PERIODES = [{ id: '1m', libelle: '1 mois', jours: 31 }, { id: '3m', libelle: '3 mois', jours: 92 }, { id: 'tout', libelle: 'Tout', jours: 10_000 }]

/* La valeur du fonds jour par jour, v1 en gris, desk de volatilité en bleu. */
export function CourbeValeur({ etat }: { etat: Etat }) {
  const [vue, setVue] = useState<'valeur' | 'resultat'>('valeur')
  const [periode, setPeriode] = useState('tout')
  const { points, debut_v2 } = etat.historique

  const donnees = useMemo(() => {
    const limite = PERIODES.find((p) => p.id === periode)!.jours
    const depuis = new Date(Date.now() - limite * 864e5).toISOString().slice(0, 10)
    const garde = points.filter((p) => p.jour >= depuis)
    const base = garde[0]?.valeur ?? 0
    const derniereV1 = garde.filter((p) => p.epoque === 'v1').at(-1)?.jour
    return garde.map((p) => {
      const y = vue === 'valeur' ? p.valeur : p.valeur - base
      // Le point de bascule appartient aux deux séries, pour que la courbe soit continue.
      return { jour: p.jour, v1: p.epoque === 'v1' ? y : null, v2: p.epoque === 'v2' || p.jour === derniereV1 ? y : null, valeur: p.valeur }
    })
  }, [points, vue, periode])

  if (points.length < 2) return null
  const premier = donnees[0], dernier = donnees.at(-1)!
  const ecart = dernier.valeur - premier.valeur
  const montreRepere = donnees.some((d) => d.jour >= debut_v2) && donnees[0].jour < debut_v2

  return (
    <section className="carte p-6 md:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="titre text-[19px] font-semibold">Valeur du fonds</p>
          <p className="chiffres mt-1 text-[14px] text-encre-2">
            <span className={`font-semibold ${ecart >= 0 ? 'text-accent' : 'text-perte'}`}>{signe(ecart)}</span>
            {' '}({signe((ecart / premier.valeur) * 100, (n) => `${nombre(Number(n.toFixed(2)))} %`)}) depuis le {dateCourte(premier.jour)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="inline-flex rounded-[10px] bg-surface-2 p-0.5" role="group" aria-label="Affichage">
            {(['valeur', 'resultat'] as const).map((v) => (
              <button key={v} onClick={() => setVue(v)} aria-pressed={vue === v}
                className={`rounded-[8px] px-3 py-1 text-[13px] font-semibold ${vue === v ? 'bg-surface text-encre shadow-sm' : 'text-encre-3'}`}>
                {v === 'valeur' ? 'Valeur' : 'Résultat'}
              </button>
            ))}
          </div>
          <div className="inline-flex rounded-[10px] bg-surface-2 p-0.5" role="group" aria-label="Période">
            {PERIODES.map((p) => (
              <button key={p.id} onClick={() => setPeriode(p.id)} aria-pressed={periode === p.id}
                className={`rounded-[8px] px-3 py-1 text-[13px] font-semibold ${periode === p.id ? 'bg-surface text-encre shadow-sm' : 'text-encre-3'}`}>
                {p.libelle}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-6 h-[280px]">
        <ResponsiveContainer>
          <AreaChart data={donnees} margin={{ left: 4, right: 18, top: 22 }}>
            <defs>
              <linearGradient id="v2" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.26} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.01} />
              </linearGradient>
              <linearGradient id="v1" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--encre-3)" stopOpacity={0.16} />
                <stop offset="100%" stopColor="var(--encre-3)" stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--ligne)" vertical={false} />
            <XAxis dataKey="jour" tick={AXE} tickLine={false} axisLine={false} tickFormatter={dateCourte} minTickGap={36} />
            <YAxis tick={AXE} tickLine={false} axisLine={false} width={84} domain={['auto', 'auto']}
              tickFormatter={(v) => (vue === 'valeur' ? dollars(v) : signe(v))} />
            {vue === 'resultat' && <ReferenceLine y={0} stroke="var(--ligne-forte)" />}
            {montreRepere && (
              <ReferenceLine x={donnees.find((d) => d.jour >= debut_v2)?.jour} stroke="var(--accent)" strokeDasharray="4 4"
                label={{ value: 'Desk de volatilité', position: 'insideTopRight', offset: 10, fill: 'var(--accent)', fontSize: 12, fontWeight: 600 }} />
            )}
            <Tooltip contentStyle={BULLE} labelFormatter={(l) => dateCourte(String(l))}
              formatter={(v, n) => [vue === 'valeur' ? dollars(Number(v)) : signe(Number(v)), n === 'v1' ? 'Arène v1' : 'Desk de volatilité']} />
            <Area type="monotone" dataKey="v1" stroke="var(--encre-3)" strokeWidth={1.75} fill="url(#v1)" connectNulls={false} />
            <Area type="monotone" dataKey="v2" stroke="var(--accent)" strokeWidth={2.25} fill="url(#v2)" connectNulls={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-3 text-[12.5px] text-encre-3">
        En gris, l'arène multi-agents (v1). En bleu, le desk de volatilité. Valeur du compte paper IBKR, relevée par le code.
      </p>
    </section>
  )
}

/* Le gain du livre à l'échéance, selon le cours de XSP. */
export function CourbeGain({ etat }: { etat: Etat }) {
  if (!etat.courbe_de_gain.length) return null
  return (
    <section className="carte p-6">
      <p className="titre text-[19px] font-semibold">Gain du livre à l'échéance</p>
      <p className="mt-1 text-[13px] text-encre-2">Selon le cours de XSP à l'échéance, tous barreaux confondus. Les ailes bornent la perte.</p>
      <div className="mt-5 h-[260px]">
        <ResponsiveContainer>
          <AreaChart data={etat.courbe_de_gain} margin={{ left: 8, right: 8, top: 8 }}>
            <defs>
              <linearGradient id="gain" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--ligne)" vertical={false} />
            <XAxis dataKey="cours" tick={AXE} tickLine={false} axisLine={false} tickFormatter={(v) => nombre(Math.round(v))} minTickGap={40} />
            <YAxis tick={AXE} tickLine={false} axisLine={false} width={70} tickFormatter={(v) => dollars(v)} />
            <ReferenceLine y={0} stroke="var(--ligne-forte)" />
            {etat.xsp && <ReferenceLine x={etat.xsp} stroke="var(--encre-3)" strokeDasharray="3 3" />}
            <Tooltip contentStyle={BULLE} formatter={(v) => [signe(Number(v)), 'Gain']} labelFormatter={(l) => `XSP à ${nombre(Number(l))}`} />
            <Area type="linear" dataKey="gain_usd" stroke="var(--accent)" strokeWidth={2} fill="url(#gain)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
