interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  colorClass?: string
}

export default function StatCard({ title, value, subtitle, colorClass = 'text-gray-900' }: StatCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <p className="text-xs text-gray-500">{title}</p>
      <p className={`mt-1 text-2xl font-semibold ${colorClass}`}>{value}</p>
      {subtitle && <p className="mt-1 text-xs text-gray-400">{subtitle}</p>}
    </div>
  )
}
