import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CRIME_BY_YEAR } from "@/lib/landing-data";

export function CrimeByYearChart({ animate }: { animate: boolean }) {
  return (
    <div className="ug-chart-wrap">
      <p className="ug-chart-title">Global Crypto Crime</p>
      <p className="ug-chart-unit">USD Billion stolen per year</p>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart
          data={CRIME_BY_YEAR}
          margin={{ top: 8, right: 8, left: -24, bottom: 0 }}
        >
          <defs>
            <linearGradient id="cbyGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.55} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="year"
            tick={{
              fill: "#4a5568",
              fontSize: 10,
              fontFamily: "IBM Plex Mono",
            }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{
              fill: "#4a5568",
              fontSize: 10,
              fontFamily: "IBM Plex Mono",
            }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `$${v}B`}
          />
          <Tooltip
            contentStyle={{
              background: "#0d1424",
              border: "1px solid #22d3ee22",
              borderRadius: 8,
              fontFamily: "IBM Plex Mono",
              fontSize: 11,
            }}
            labelStyle={{ color: "#f0f4ff" }}
            itemStyle={{ color: "#22d3ee" }}
            formatter={(v: number) => [`$${v}B`, "Stolen"]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#22d3ee"
            strokeWidth={2}
            fill="url(#cbyGrad)"
            isAnimationActive={animate}
            animationDuration={1200}
            animationEasing="ease-out"
            dot={{ fill: "#22d3ee", r: 3, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
