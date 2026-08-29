import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FROZEN_FUNDS } from "@/lib/landing-data";

export function FrozenFundsChart({ animate }: { animate: boolean }) {
  return (
    <div className="ug-chart-wrap">
      <p className="ug-chart-title">Funds Frozen via Argus</p>
      <p className="ug-chart-unit">₹ Crore — rolling 12 months</p>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart
          data={FROZEN_FUNDS}
          margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
        >
          <defs>
            <linearGradient id="frozenGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f5a524" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#f5a524" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="month"
            tick={{ fill: "#4a5568", fontSize: 9, fontFamily: "IBM Plex Mono" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#4a5568", fontSize: 9, fontFamily: "IBM Plex Mono" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `₹${v}Cr`}
          />
          <Tooltip
            contentStyle={{
              background: "#0d1424",
              border: "1px solid #f5a52422",
              borderRadius: 8,
              fontFamily: "IBM Plex Mono",
              fontSize: 11,
            }}
            labelStyle={{ color: "#f0f4ff" }}
            itemStyle={{ color: "#f5a524" }}
            formatter={(v: number) => [`₹${v} Cr`, "Frozen"]}
          />
          <Area
            type="monotone"
            dataKey="crore"
            stroke="#f5a524"
            strokeWidth={2}
            fill="url(#frozenGrad)"
            isAnimationActive={animate}
            animationDuration={1400}
            animationEasing="ease-out"
            dot={{ fill: "#f5a524", r: 2.5, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
