import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { AxiosError } from 'axios'
import { useForm } from 'react-hook-form'
import type { ApiResult } from '@/types/api'
import { cn } from '@/lib/utils'
import {
  dictTypeFormSchema,
  extractDictTypeServerErrors,
  type DictTypeForm,
  type DictTypeFormValues,
} from '../form'
import {
  buildDictTypeFormDefaults,
  type DictType,
  type DictTypeFormInput,
} from '../model'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { SelectDropdown } from '@/components/select-dropdown'

type DictTypeDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialData?: DictType
  isSaving: boolean
  onSubmit: (values: DictTypeFormInput) => Promise<void>
}

function RequiredFormLabel({ children }: { children: string }) {
  return (
    <FormLabel className='flex items-center gap-1'>
      <span className='text-destructive'>*</span>
      <span>{children}</span>
    </FormLabel>
  )
}

export function DictTypeDialog({
  open,
  onOpenChange,
  initialData,
  isSaving,
  onSubmit,
}: DictTypeDialogProps) {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const form = useForm<DictTypeFormValues, undefined, DictTypeForm>({
    resolver: zodResolver(dictTypeFormSchema),
    defaultValues: buildDictTypeFormDefaults(initialData),
  })

  useEffect(() => {
    form.reset(buildDictTypeFormDefaults(initialData))
  }, [form, initialData, open])

  async function handleSubmit(values: DictTypeForm) {
    form.clearErrors()
    setSubmitError(null)

    try {
      await onSubmit(values)
      onOpenChange(false)
    } catch (error) {
      if (error instanceof AxiosError) {
        const message = (error.response?.data as ApiResult<unknown> | undefined)
          ?.message
        const { fieldErrors, generalErrors } = extractDictTypeServerErrors(message)

        let hasFieldError = false
        for (const [field, fieldMessage] of Object.entries(fieldErrors)) {
          if (!fieldMessage) {
            continue
          }

          form.setError(field as keyof DictTypeFormValues, {
            type: 'server',
            message: fieldMessage,
          })
          hasFieldError = true
        }

        if (generalErrors.length > 0) {
          setSubmitError(generalErrors[0])
          return
        }

        if (hasFieldError) {
          setSubmitError(null)
          return
        }
      }

      setSubmitError('保存失败，请重试。')
    }
  }

  const isEditing = Boolean(initialData?.id)

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          setSubmitError(null)
        }
        onOpenChange(nextOpen)
      }}
    >
      <DialogContent className='sm:max-w-[520px]'>
        <DialogHeader>
          <DialogTitle>{isEditing ? '编辑字典分组' : '新增字典分组'}</DialogTitle>
          <DialogDescription>
            分组编码会作为右侧字典项的归属标识，创建后建议保持稳定。
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            id='dict-type-form'
            onSubmit={form.handleSubmit(handleSubmit)}
            className='space-y-4'
          >
            <div className='grid gap-4 md:grid-cols-2'>
              <FormField
                control={form.control}
                name='dictName'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>分组名称</RequiredFormLabel>
                    <FormControl>
                      <Input placeholder='例如：产业领域' disabled={isSaving} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='dictType'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>分组编码</RequiredFormLabel>
                    <FormControl>
                      <Input
                        placeholder='例如：industry_field'
                        disabled={isSaving || isEditing}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='status'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>分组状态</RequiredFormLabel>
                    <SelectDropdown
                      isControlled
                      value={field.value}
                      onValueChange={field.onChange}
                      items={[
                        { label: '正常', value: '1' },
                        { label: '停用', value: '0' },
                      ]}
                      disabled={isSaving}
                      className='w-full'
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name='remark'
              render={({ field }) => (
                <FormItem>
                  <FormLabel>备注</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={4}
                      placeholder='补充分组说明，方便后续维护'
                      disabled={isSaving}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <p
              className={cn(
                'min-h-4 text-right text-xs text-destructive',
                !submitError && 'select-none text-transparent'
              )}
            >
              {submitError || '\u00A0'}
            </p>
          </form>
        </Form>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
          >
            取消
          </Button>
          <Button form='dict-type-form' type='submit' disabled={isSaving}>
            {isEditing ? '保存分组' : '创建分组'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
