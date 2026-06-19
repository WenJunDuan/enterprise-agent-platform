import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SelectDropdown } from '@/components/select-dropdown'

export type LoginLogSearchFormState = {
  username: string
  ipaddr: string
  status: string
  beginTime: string
  endTime: string
}

const ALL_VALUE = '__all__'

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
      <SelectDropdown
        value={value.status || ALL_VALUE}
        onValueChange={(next) =>
          onChange({ ...value, status: next === ALL_VALUE ? '' : next })
        }
        items={[
          { label: '全部状态', value: ALL_VALUE },
          { label: '成功', value: '0' },
          { label: '失败', value: '1' },
        ]}
        isControlled
        withFormControl={false}
        className='h-9 w-32'
      />
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
