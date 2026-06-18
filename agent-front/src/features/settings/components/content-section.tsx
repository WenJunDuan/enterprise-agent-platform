import { Separator } from '@/components/ui/separator'

type ContentSectionProps = {
  title?: string
  desc?: string
  children: React.JSX.Element
}

export function ContentSection({ title, desc, children }: ContentSectionProps) {
  return (
    <div className='flex flex-1 flex-col'>
      {(title || desc) && (
        <>
          <div className='flex-none'>
            {title && <h3 className='text-lg font-medium'>{title}</h3>}
            {desc && <p className='text-sm text-muted-foreground'>{desc}</p>}
          </div>
          <Separator className='my-4 flex-none' />
        </>
      )}
      <div className='w-full pe-4 pb-12'>
        <div className='-mx-1 px-1.5 lg:max-w-xl'>{children}</div>
      </div>
    </div>
  )
}
