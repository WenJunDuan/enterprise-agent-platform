import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'

type MetricCardProps = {
  label: string
  value: string | number
  icon: LucideIcon
}

export function MetricCard({ label, value, icon: Icon }: MetricCardProps) {
  return (
    <Card>
      <CardContent className='flex items-center justify-between p-4'>
        <div>
          <p className='text-sm text-muted-foreground'>{label}</p>
          <p className='mt-1 text-2xl font-semibold'>{value}</p>
        </div>
        <Icon className='size-8 text-muted-foreground' />
      </CardContent>
    </Card>
  )
}
