import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SelectDropdown } from '@/components/select-dropdown'
import { BUSINESS_TYPE_OPTIONS } from '../data/business-type'

export type OperLogSearchFormState = {
  title: string
  operName: string
  businessType: string
  status: string
  beginTime: string
  endTime: string
}

const ALL_VALUE = '__all__'

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
      <SelectDropdown
        value={value.businessType || ALL_VALUE}
        onValueChange={(next) =>
          onChange({ ...value, businessType: next === ALL_VALUE ? '' : next })
        }
        items={[
          { label: '全部业务类型', value: ALL_VALUE },
          ...BUSINESS_TYPE_OPTIONS.map((option) => ({
            label: option.label,
            value: String(option.value),
          })),
        ]}
        isControlled
        withFormControl={false}
        className='h-9 w-40'
      />
      <SelectDropdown
        value={value.status || ALL_VALUE}
        onValueChange={(next) =>
          onChange({ ...value, status: next === ALL_VALUE ? '' : next })
        }
        items={[
          { label: '全部状态', value: ALL_VALUE },
          { label: '正常', value: '0' },
          { label: '异常', value: '1' },
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
