import { Loader } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FormControl } from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type SelectDropdownProps = {
  onValueChange?: (value: string) => void
  defaultValue?: string
  value?: string
  placeholder?: string
  isPending?: boolean
  items: { label: string; value: string }[] | undefined
  disabled?: boolean
  className?: string
  isControlled?: boolean
  withFormControl?: boolean
}

export function SelectDropdown({
  value,
  defaultValue,
  onValueChange,
  isPending,
  items,
  placeholder,
  disabled,
  className = '',
  isControlled = false,
  withFormControl = true,
}: SelectDropdownProps) {
  const normalizedValue = value === '' ? undefined : value
  const normalizedDefaultValue = defaultValue === '' ? undefined : defaultValue
  const resolvedValue = normalizedValue ?? normalizedDefaultValue
  const defaultState = isControlled
    ? { value: resolvedValue, onValueChange }
    : { defaultValue: resolvedValue, onValueChange }
  const trigger = (
    <SelectTrigger disabled={disabled} className={cn(className)}>
      <SelectValue placeholder={placeholder ?? '请选择'} />
    </SelectTrigger>
  )

  return (
    <Select
      key={
        isControlled
          ? `${resolvedValue ?? ''}:${items?.length ?? 0}`
          : undefined
      }
      {...defaultState}
    >
      {withFormControl ? <FormControl>{trigger}</FormControl> : trigger}
      <SelectContent>
        {isPending ? (
          <SelectItem disabled value='loading' className='h-14'>
            <div className='flex items-center justify-center gap-2'>
              <Loader className='h-5 w-5 animate-spin' />
              {'  '}
              加载中...
            </div>
          </SelectItem>
        ) : (
          items?.map(({ label, value }) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  )
}
