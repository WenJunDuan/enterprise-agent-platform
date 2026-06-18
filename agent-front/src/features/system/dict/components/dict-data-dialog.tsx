import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { AxiosError } from 'axios'
import { useForm } from 'react-hook-form'
import type { ApiResult } from '@/types/api'
import { cn } from '@/lib/utils'
import {
  dictDataFormSchema,
  extractDictDataServerErrors,
  type DictDataForm,
  type DictDataFormValues,
} from '../form'
import {
  buildDictDataFormDefaults,
  type DictData,
  type DictDataFormInput,
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

type DictDataDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  dictType: string
  initialData?: DictData
  isSaving: boolean
  onSubmit: (values: DictDataFormInput) => Promise<void>
}

function RequiredFormLabel({ children }: { children: string }) {
  return (
    <FormLabel className='flex items-center gap-1'>
      <span className='text-destructive'>*</span>
      <span>{children}</span>
    </FormLabel>
  )
}

export function DictDataDialog({
  open,
  onOpenChange,
  dictType,
  initialData,
  isSaving,
  onSubmit,
}: DictDataDialogProps) {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const form = useForm<DictDataFormValues, undefined, DictDataForm>({
    resolver: zodResolver(dictDataFormSchema),
    defaultValues: buildDictDataFormDefaults(dictType, initialData),
  })

  useEffect(() => {
    form.reset(buildDictDataFormDefaults(dictType, initialData))
  }, [dictType, form, initialData, open])

  async function handleSubmit(values: DictDataForm) {
    form.clearErrors()
    setSubmitError(null)

    try {
      await onSubmit(values)
      onOpenChange(false)
    } catch (error) {
      if (error instanceof AxiosError) {
        const message = (error.response?.data as ApiResult<unknown> | undefined)
          ?.message
        const { fieldErrors, generalErrors } = extractDictDataServerErrors(message)

        let hasFieldError = false
        for (const [field, fieldMessage] of Object.entries(fieldErrors)) {
          if (!fieldMessage) {
            continue
          }

          form.setError(field as keyof DictDataFormValues, {
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
      <DialogContent className='sm:max-w-[640px]'>
        <DialogHeader>
          <DialogTitle>{isEditing ? '编辑字典项' : '新增字典项'}</DialogTitle>
          <DialogDescription>
            当前分组：<span className='font-medium text-foreground'>{dictType}</span>
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            id='dict-data-form'
            onSubmit={form.handleSubmit(handleSubmit)}
            className='space-y-4'
          >
            <div className='grid gap-4 md:grid-cols-2'>
              <FormField
                control={form.control}
                name='dictLabel'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>字典名称</RequiredFormLabel>
                    <FormControl>
                      <Input placeholder='例如：人工智能' disabled={isSaving} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='dictValue'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>字典编码</RequiredFormLabel>
                    <FormControl>
                      <Input placeholder='例如：ai' disabled={isSaving} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='dictSort'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>排序</RequiredFormLabel>
                    <FormControl>
                      <Input inputMode='numeric' placeholder='0' disabled={isSaving} {...field} />
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
                    <RequiredFormLabel>状态</RequiredFormLabel>
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

              <FormField
                control={form.control}
                name='isDefault'
                render={({ field }) => (
                  <FormItem>
                    <RequiredFormLabel>默认项</RequiredFormLabel>
                    <SelectDropdown
                      isControlled
                      value={field.value}
                      onValueChange={field.onChange}
                      items={[
                        { label: '否', value: 'N' },
                        { label: '是', value: 'Y' },
                      ]}
                      disabled={isSaving}
                      className='w-full'
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='cssClass'
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>标签样式</FormLabel>
                    <FormControl>
                      <Input placeholder='例如：primary' disabled={isSaving} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='listClass'
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>列表样式</FormLabel>
                    <FormControl>
                      <Input placeholder='例如：success' disabled={isSaving} {...field} />
                    </FormControl>
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
                    <Textarea rows={4} placeholder='补充说明' disabled={isSaving} {...field} />
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
          <Button form='dict-data-form' type='submit' disabled={isSaving}>
            {isEditing ? '保存字典项' : '创建字典项'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
