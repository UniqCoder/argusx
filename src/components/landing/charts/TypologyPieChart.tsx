import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { TYPOLOGY_DATA } from "@/lib/landing-data";

export function TypologyPieChart({ animate }: { animate: boolean }) {
  return (
    <div className="ug-chart-wrap">
      <p className="ug-chart-title">Fraud by Typology</p>
      <p className="ug-chart-unit">% of reported cases (2024)</p>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={TYPOLOGY_DATA}
            cx="50%"
            cy="50%"
            innerRadius={42}
            outerRadius={68}
            paddingAngle={3}
            dataKey="value"
            isAnimationActive={animate}
            animationDuration={1000}
            animationEasing="ease-out"
            strokeWidth={0}
          >
            {TYPOLOGY_DATA.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "#0d1424",
              border: "1px solid #f5a52422",
              borderRadius: 8,
              fontFamily: "IBM Plex Mono",
              fontSize: 11,
            }}
            itemStyle={{ color: "#f0f4ff" }}
            formatter={(v: number) => [`${v}%`, ""]}
          />
          <Legend
            iconType="circle"
            iconSize={7}
            formatter={(value) => (
              <span
                style={{
                  color: "#4a5568",
                  fontSize: 9,
                  fontFamily: "IBM Plex Mono",
                  letterSpacing: "0.06em",
                }}
              >
                {value.toUpperCase()}
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
