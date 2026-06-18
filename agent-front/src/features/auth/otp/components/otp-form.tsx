import { useState } from 'react'
import { z } from 'zod'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from '@tanstack/react-router'
import { loginWithTenantPin } from '@/app/auth/session'
import { Loader2, LogIn } from 'lucide-react'
import { handleServerError } from '@/lib/handle-server-error'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from '@/components/ui/input-otp'
import { getConfiguredTenantPinLength } from '@/features/audit/api'

const pinLength = getConfiguredTenantPinLength()
const formSchema = z.object({
  pin: z
    .string()
    .trim()
    .min(pinLength, `请输入 ${pinLength} 位访问 PIN。`)
    .max(pinLength, `请输入 ${pinLength} 位访问 PIN。`),
})

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '登录失败，请重试。'
}

type OtpFormProps = React.HTMLAttributes<HTMLFormElement> & {
  redirectTo?: string
}

export function OtpForm({ className, redirectTo, ...props }: OtpFormProps) {
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: { pin: '' },
  })

  // eslint-disable-next-line react-hooks/incompatible-library
  const pin = form.watch('pin')

  async function onSubmit(data: z.infer<typeof formSchema>) {
    setIsLoading(true)

    try {
      const user = await loginWithTenantPin(data.pin)
      if (!user) return

      navigate({
        to: redirectTo || '/',
        replace: true,
      })
    } catch (error) {
      const message = getErrorMessage(error)
      handleServerError(error)
      form.setError('pin', { message })
      form.setValue('pin', '', {
        shouldDirty: true,
        shouldTouch: true,
        shouldValidate: false,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const slots = Array.from({ length: pinLength }, (_, index) => index)
  const leftSlots = slots.slice(0, Math.ceil(pinLength / 2))
  const rightSlots = slots.slice(Math.ceil(pinLength / 2))

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className={cn('grid gap-2', className)}
        {...props}
      >
        <FormField
          control={form.control}
          name='pin'
          render={({ field }) => (
            <FormItem>
              <FormLabel className='sr-only'>访问 PIN</FormLabel>
              <FormControl>
                <InputOTP
                  maxLength={pinLength}
                  {...field}
                  containerClassName='justify-between sm:[&>[data-slot="input-otp-group"]>div]:w-12'
                >
                  <InputOTPGroup>
                    {leftSlots.map((slot) => (
                      <InputOTPSlot key={slot} index={slot} mask />
                    ))}
                  </InputOTPGroup>
                  {rightSlots.length > 0 && (
                    <>
                      <InputOTPSeparator />
                      <InputOTPGroup>
                        {rightSlots.map((slot) => (
                          <InputOTPSlot key={slot} index={slot} mask />
                        ))}
                      </InputOTPGroup>
                    </>
                  )}
                </InputOTP>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button className='mt-2' disabled={pin.length < pinLength || isLoading}>
          {isLoading ? <Loader2 className='animate-spin' /> : <LogIn />}
          登录
        </Button>
      </form>
    </Form>
  )
}
