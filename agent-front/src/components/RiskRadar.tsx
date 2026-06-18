interface Dimension {
  name: string
  score: number
}

interface RiskRadarProps {
  dimensions: Dimension[]
}

const LABEL_MAP: Record<string, string> = {
  invoice: '发票',
  amount: '金额',
  approval: '审批',
  budget: '预算',
  anomaly: '异常',
}

function polarToCartesian(cx: number, cy: number, r: number, angleRad: number) {
  return {
    x: cx + r * Math.sin(angleRad),
    y: cy - r * Math.cos(angleRad),
  }
}

export default function RiskRadar({ dimensions }: RiskRadarProps) {
  if (!dimensions || dimensions.length === 0) return null

  const size = 200
  const cx = size / 2
  const cy = size / 2
  const maxR = 70
  const n = dimensions.length
  const angles = dimensions.map((_, i) => (2 * Math.PI * i) / n)

  // Grid circles
  const gridLevels = [2, 4, 6, 8, 10]

  // Polygon points for data
  const dataPoints = dimensions.map((dim, i) => {
    const r = (Math.min(10, Math.max(0, dim.score)) / 10) * maxR
    return polarToCartesian(cx, cy, r, angles[i])
  })
  const dataPolygon = dataPoints.map(p => `${p.x},${p.y}`).join(' ')

  // Axis lines and label positions
  const labelR = maxR + 18

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-label="风险雷达图">
      {/* Grid circles */}
      {gridLevels.map(level => {
        const r = (level / 10) * maxR
        return (
          <circle
            key={level}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth={0.75}
          />
        )
      })}

      {/* Axis lines */}
      {angles.map((angle, i) => {
        const outer = polarToCartesian(cx, cy, maxR, angle)
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={outer.x}
            y2={outer.y}
            stroke="#d1d5db"
            strokeWidth={0.75}
          />
        )
      })}

      {/* Data polygon */}
      <polygon
        points={dataPolygon}
        fill="rgba(59,130,246,0.15)"
        stroke="#3b82f6"
        strokeWidth={1.5}
        strokeLinejoin="round"
      />

      {/* Data points */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="#3b82f6" />
      ))}

      {/* Labels */}
      {dimensions.map((dim, i) => {
        const lp = polarToCartesian(cx, cy, labelR, angles[i])
        const label = LABEL_MAP[dim.name] ?? dim.name
        return (
          <text
            key={i}
            x={lp.x}
            y={lp.y}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={9}
            fill="#6b7280"
            fontFamily="system-ui,sans-serif"
          >
            {label} {dim.score}
          </text>
        )
      })}
    </svg>
  )
}
