import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export type LoginLogSearchFormState = {
  username: string
  ipaddr: string
  status: string
  beginTime: string
  endTime: string
}

type Props = {
  value: LoginLogSearchFormState
  onChange: (next: LoginLogSearchFormState) => void
  onSubmit: () => void
  onReset: () => void
}

export function LoginLogSearchForm({
  value,
  onChange,
  onSubmit,
  onReset,
}: Props) {
  return (
    <div className='flex flex-wrap items-end gap-2 rounded-md border bg-card p-3'>
      <Input
        placeholder='账号'
        className='w-40'
        value={value.username}
        onChange={(e) => onChange({ ...value, username: e.target.value })}
      />
      <Input
        placeholder='IP'
        className='w-40'
        value={value.ipaddr}
        onChange={(e) => onChange({ ...value, ipaddr: e.target.value })}
      />
      <select
        className='h-9 rounded-md border bg-background px-3 text-sm'
        value={value.status}
        onChange={(e) => onChange({ ...value, status: e.target.value })}
      >
        <option value=''>全部状态</option>
        <option value='0'>成功</option>
        <option value='1'>失败</option>
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
