interface SkeletonProps {
  className?: string
  lines?: number
}

export function SkeletonLine({ className = '' }: { className?: string }) {
  return <div className={`h-4 bg-gray-100 rounded animate-pulse ${className}`} />
}

export default function Skeleton({ lines = 4, className = '' }: SkeletonProps) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine key={i} className={i === 0 ? 'w-1/2' : i % 3 === 0 ? 'w-3/4' : ''} />
      ))}
    </div>
  )
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white p-6 ${className}`}>
      <Skeleton lines={4} />
    </div>
  )
}
