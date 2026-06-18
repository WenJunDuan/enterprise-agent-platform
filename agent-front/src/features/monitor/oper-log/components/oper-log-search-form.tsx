import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BUSINESS_TYPE_OPTIONS } from '../data/business-type'

export type OperLogSearchFormState = {
  title: string
  operName: string
  businessType: string
  status: string
  beginTime: string
  endTime: string
}

type Props = {
  value: OperLogSearchFormState
  onChange: (next: OperLogSearchFormState) => void
  onSubmit: () => void
  onReset: () => void
}

export function OperLogSearchForm({ value, onChange, onSubmit, onReset }: Props) {
  return (
    <div className='flex flex-wrap items-end gap-2 rounded-md border bg-card p-3'>
      <Input
        placeholder='模块'
        className='w-36'
        value={value.title}
        onChange={(e) => onChange({ ...value, title: e.target.value })}
      />
      <Input
        placeholder='操作人'
        className='w-36'
        value={value.operName}
        onChange={(e) => onChange({ ...value, operName: e.target.value })}
      />
      <select
        className='h-9 rounded-md border bg-background px-3 text-sm'
        value={value.businessType}
        onChange={(e) => onChange({ ...value, businessType: e.target.value })}
      >
        <option value=''>全部业务类型</option>
        {BUSINESS_TYPE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <select
        className='h-9 rounded-md border bg-background px-3 text-sm'
        value={value.status}
        onChange={(e) => onChange({ ...value, status: e.target.value })}
      >
        <option value=''>全部状态</option>
        <option value='0'>正常</option>
        <option value='1'>异常</option>
      </select>
      <Input
        type='datetime-local'
        className='w-52'
        value={value.beginTime}
        onChange={(e) => onChange({ ...value, beginTime: e.target.value })}
      />
      <Input
        type='datetime-local'
        className='w-52'
        value={value.endTime}
        onChange={(e) => onChange({ ...value, endTime: e.target.value })}
      />
      <Button size='sm' onClick={onSubmit}>
        查询
      </Button>
      <Button size='sm' variant='outline' onClick={onReset}>
        重置
      </Button>
    </div>
  )
}
