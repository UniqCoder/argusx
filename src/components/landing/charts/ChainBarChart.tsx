import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHAIN_DATA } from "@/lib/landing-data";

export function ChainBarChart({ animate }: { animate: boolean }) {
  return (
    <div className="ug-chart-wrap">
      <p className="ug-chart-title">Fraud Volume by Chain</p>
      <p className="ug-chart-unit">USD Billion — 2022 / 2023 / 2024</p>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart
          data={CHAIN_DATA}
          margin={{ top: 8, right: 8, left: -24, bottom: 0 }}
          barGap={2}
        >
          <XAxis
            dataKey="chain"
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
              border: "1px solid #f5a52422",
              borderRadius: 8,
              fontFamily: "IBM Plex Mono",
              fontSize: 11,
            }}
            labelStyle={{ color: "#f0f4ff" }}
            itemStyle={{ color: "#f0f4ff" }}
            formatter={(v: number) => [`$${v}B`]}
          />
          <Legend
            iconType="circle"
            iconSize={6}
            formatter={(val) => (
              <span
                style={{
                  color: "#4a5568",
                  fontSize: 9,
                  fontFamily: "IBM Plex Mono",
                }}
              >
                {val}
              </span>
            )}
          />
          <Bar
            dataKey="2022"
            fill="#4a5568"
            radius={[3, 3, 0, 0]}
            isAnimationActive={animate}
            animationDuration={900}
            animationEasing="ease-out"
          />
          <Bar
            dataKey="2023"
            fill="#22d3ee"
            radius={[3, 3, 0, 0]}
            isAnimationActive={animate}
            animationDuration={1000}
            animationEasing="ease-out"
          />
          <Bar
            dataKey="2024"
            fill="#f5a524"
            radius={[3, 3, 0, 0]}
            isAnimationActive={animate}
            animationDuration={1100}
            animationEasing="ease-out"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
