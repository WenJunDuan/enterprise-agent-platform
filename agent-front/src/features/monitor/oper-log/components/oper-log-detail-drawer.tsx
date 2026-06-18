import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { getBusinessTypeMeta } from '../data/business-type'
import { formatDateTime, tryFormatJson, type OperLog } from '../model'

type Props = {
  log: OperLog | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function Field({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <div className='grid grid-cols-3 gap-3 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='col-span-2 break-all'>{value ?? '-'}</span>
    </div>
  )
}

export function OperLogDetailDrawer({ log, open, onOpenChange }: Props) {
  const meta = log ? getBusinessTypeMeta(log.businessType) : null

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='flex w-full max-w-xl flex-col gap-3 overflow-hidden sm:max-w-xl'>
        <SheetHeader>
          <SheetTitle>操作日志详情</SheetTitle>
          <SheetDescription>
            {log ? `ID: ${log.operId}` : '加载中...'}
          </SheetDescription>
        </SheetHeader>

        <div className='flex-1 space-y-3 overflow-auto px-4'>
          {log ? (
            <>
              <Field label='模块' value={log.title} />
              <Field
                label='业务类型'
                value={
                  meta ? (
                    <Badge variant={meta.variant}>{meta.label}</Badge>
                  ) : (
                    log.businessType
                  )
                }
              />
              <Field
                label='状态'
                value={
                  <Badge
                    variant={log.status === 0 ? 'default' : 'destructive'}
                  >
                    {log.status === 0 ? '正常' : '异常'}
                  </Badge>
                }
              />
              <Field label='操作人' value={log.operName} />
              <Field label='部门' value={log.deptName} />
              <Field label='请求方式' value={log.requestMethod} />
              <Field label='方法' value={log.method} />
              <Field label='URL' value={log.operUrl} />
              <Field label='IP' value={log.operIp} />
              <Field label='地点' value={log.operLocation} />
              <Field label='耗时' value={`${log.costTime} ms`} />
              <Field label='时间' value={formatDateTime(log.operTime)} />

              <div className='text-sm'>
                <div className='mb-1 text-muted-foreground'>请求参数</div>
                <pre className='max-h-60 overflow-auto rounded bg-muted p-2 text-xs whitespace-pre-wrap break-all'>
                  {tryFormatJson(log.operParam) || '(空)'}
                </pre>
              </div>

              <div className='text-sm'>
                <div className='mb-1 text-muted-foreground'>响应结果</div>
                <pre className='max-h-60 overflow-auto rounded bg-muted p-2 text-xs whitespace-pre-wrap break-all'>
                  {tryFormatJson(log.jsonResult) || '(空)'}
                </pre>
              </div>

              {log.errorMsg ? (
                <div className='text-sm'>
                  <div className='mb-1 text-destructive'>错误信息</div>
                  <pre className='max-h-40 overflow-auto rounded border border-destructive/30 bg-destructive/5 p-2 text-xs whitespace-pre-wrap break-all'>
                    {log.errorMsg}
                  </pre>
                </div>
              ) : null}
            </>
          ) : null}
        </div>

        <SheetFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
