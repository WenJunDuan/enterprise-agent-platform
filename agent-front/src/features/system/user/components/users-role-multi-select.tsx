import { CheckIcon, PlusCircledIcon } from '@radix-ui/react-icons'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'

type UsersRoleMultiSelectProps = {
  value: string[]
  onChange: (value: string[]) => void
  options: { label: string; value: string }[]
  placeholder?: string
  disabled?: boolean
  isPending?: boolean
}

export function UsersRoleMultiSelect({
  value,
  onChange,
  options,
  placeholder = '请选择角色',
  disabled,
  isPending,
}: UsersRoleMultiSelectProps) {
  const selectedValues = new Set(value)

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type='button'
          variant='outline'
          role='combobox'
          disabled={disabled}
          className={cn(
            'min-h-10 w-full justify-start gap-2 px-3',
            value.length === 0 && 'text-muted-foreground'
          )}
        >
          <PlusCircledIcon className='size-4 shrink-0' />
          {isPending ? (
            '角色加载中...'
          ) : value.length === 0 ? (
            placeholder
          ) : value.length > 2 ? (
            <Badge variant='secondary'>已选 {value.length} 项</Badge>
          ) : (
            <span className='truncate'>
              {options
                .filter((option) => selectedValues.has(option.value))
                .map((option) => option.label)
                .join('、')}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-[320px] p-0' align='start'>
        <Command>
          <CommandInput placeholder='搜索角色...' />
          <CommandList>
            <CommandEmpty>未找到角色。</CommandEmpty>
            <CommandGroup>
              {options.map((option) => {
                const isSelected = selectedValues.has(option.value)
                return (
                  <CommandItem
                    key={option.value}
                    value={option.label}
                    onSelect={() => {
                      const nextValues = isSelected
                        ? value.filter((item) => item !== option.value)
                        : [...value, option.value]
                      onChange(nextValues)
                    }}
                  >
                    <div
                      className={cn(
                        'flex size-4 items-center justify-center rounded-sm border border-primary',
                        isSelected
                          ? 'bg-primary text-primary-foreground'
                          : 'opacity-50 [&_svg]:invisible'
                      )}
                    >
                      <CheckIcon className='size-3.5 text-background' />
                    </div>
                    <span>{option.label}</span>
                  </CommandItem>
                )
              })}
            </CommandGroup>
            {value.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup>
                  <CommandItem
                    onSelect={() => onChange([])}
                    className='justify-center text-center'
                  >
                    清空已选角色
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
        <Separator />
        <div className='px-3 py-2 text-xs text-muted-foreground'>
          支持多选，提交时会按所选角色 ID 保存。
        </div>
      </PopoverContent>
    </Popover>
  )
}
