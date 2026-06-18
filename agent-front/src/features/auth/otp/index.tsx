import { useSearch } from '@tanstack/react-router'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { AuthLayout } from '../components/auth-layout'
import { OtpForm } from './components/otp-form'

export function Otp() {
  const { redirect } = useSearch({ from: '/(auth)/otp' })

  return (
    <AuthLayout>
      <Card className='gap-4'>
        <CardHeader>
          <CardTitle className='text-base tracking-tight'>
            平台授权访问
          </CardTitle>
          <CardDescription>
            请输入访问 PIN。
            <br />
            验证通过后进入工作台。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <OtpForm redirectTo={redirect} />
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
