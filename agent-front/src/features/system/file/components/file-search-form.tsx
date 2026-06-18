import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BIZ_TYPE_OPTIONS } from '../model'

export type FileSearchState = {
  originalName: string
  extension: string
  bizType: string
}

type Props = {
  value: FileSearchState
  onChange: (next: FileSearchState) => void
  onSubmit: () => void
  onReset: () => void
}

export function FileSearchForm({ value, onChange, onSubmit, onReset }: Props) {
  return (
    <div className='flex flex-wrap items-end gap-2 rounded-md border bg-card p-3'>
      <Input
        placeholder='文件名'
        className='w-40'
        value={value.originalName}
        onChange={(e) => onChange({ ...value, originalName: e.target.value })}
      />
      <Input
        placeholder='扩展名 (如 pdf)'
        className='w-36'
        value={value.extension}
        onChange={(e) =>
          onChange({ ...value, extension: e.target.value.toLowerCase() })
        }
      />
      <select
        className='h-9 rounded-md border bg-background px-3 text-sm'
        value={value.bizType}
        onChange={(e) => onChange({ ...value, bizType: e.target.value })}
      >
        <option value=''>全部业务类型</option>
        {BIZ_TYPE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <Button size='sm' onClick={onSubmit}>
        查询
      </Button>
      <Button size='sm' variant='outline' onClick={onReset}>
        重置
      </Button>
    </div>
  )
}
