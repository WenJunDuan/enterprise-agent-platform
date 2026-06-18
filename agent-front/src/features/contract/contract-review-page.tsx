import { FileText, Upload } from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

export function ContractReviewPage() {
  return (
    <>
      <Header fixed />
      <Main constrained className='space-y-5'>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>合同审查清单</h1>
          <p className='text-sm text-muted-foreground'>
            上传合同材料，查看审查进度与结论。
          </p>
        </div>

        <Alert>
          <AlertDescription>
            合同审查入口已就绪，当前能力正在接入中。
          </AlertDescription>
        </Alert>

        <Card>
          <CardHeader>
            <CardTitle>审查材料</CardTitle>
            <CardDescription>支持合同正文、补充协议和相关附件。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className='flex min-h-48 flex-col items-center justify-center gap-4 rounded-lg border border-dashed bg-muted/20 p-6 text-center'>
              <FileText className='size-10 text-muted-foreground' />
              <div>
                <div className='font-medium'>暂未开放上传</div>
                <div className='mt-1 text-sm text-muted-foreground'>
                  开放后可在此提交合同审查材料。
                </div>
              </div>
              <Button disabled>
                <Upload className='size-4' />
                上传合同
              </Button>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
