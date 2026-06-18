import { type SVGProps } from 'react'
import { Root as Radio, Item } from '@radix-ui/react-radio-group'
import { fonts } from '@/config/fonts'
import { CircleCheck, RotateCcw, Settings } from 'lucide-react'
import { IconDir } from '@/assets/custom/icon-dir'
import { IconLayoutCompact } from '@/assets/custom/icon-layout-compact'
import { IconLayoutDefault } from '@/assets/custom/icon-layout-default'
import { IconLayoutFull } from '@/assets/custom/icon-layout-full'
import { IconSidebarFloating } from '@/assets/custom/icon-sidebar-floating'
import { IconSidebarInset } from '@/assets/custom/icon-sidebar-inset'
import { IconSidebarSidebar } from '@/assets/custom/icon-sidebar-sidebar'
import { IconThemeDark } from '@/assets/custom/icon-theme-dark'
import { IconThemeLight } from '@/assets/custom/icon-theme-light'
import { IconThemeSystem } from '@/assets/custom/icon-theme-system'
import { cn } from '@/lib/utils'
import { useAccessibility } from '@/context/accessibility-provider'
import { useDirection } from '@/context/direction-provider'
import { useFont } from '@/context/font-provider'
import { type Collapsible, useLayout } from '@/context/layout-provider'
import { useTheme } from '@/context/theme-provider'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useSidebar } from './ui/sidebar'

type ConfigDrawerProps = {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  hideTrigger?: boolean
}

export function ConfigDrawer({
  open,
  onOpenChange,
  hideTrigger = false,
}: ConfigDrawerProps) {
  const { setOpen } = useSidebar()
  const { resetAccessibility } = useAccessibility()
  const { resetDir } = useDirection()
  const { resetTheme } = useTheme()
  const { resetLayout } = useLayout()

  const handleReset = () => {
    setOpen(true)
    resetAccessibility()
    resetDir()
    resetTheme()
    resetLayout()
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {!hideTrigger && (
        <SheetTrigger asChild>
          <Button
            size='icon'
            variant='ghost'
            aria-label='打开布局设置'
            aria-describedby='config-drawer-description'
            className='rounded-full'
          >
            <Settings aria-hidden='true' />
          </Button>
        </SheetTrigger>
      )}
      <SheetContent className='flex flex-col'>
        <SheetHeader className='pb-0 text-start'>
          <SheetTitle>布局设置</SheetTitle>
          <SheetDescription id='config-drawer-description'>
            调整主题、侧边栏、布局和页面方向。
          </SheetDescription>
        </SheetHeader>
        <div className='space-y-6 overflow-y-auto px-4'>
          <AccessibilityConfig />
          <FontConfig />
          <ThemeConfig />
          <SidebarConfig />
          <LayoutConfig />
          <DirConfig />
        </div>
        <SheetFooter className='gap-2'>
          <Button
            variant='destructive'
            onClick={handleReset}
            aria-label='恢复所有默认设置'
          >
            恢复默认
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function AccessibilityConfig() {
  const { elderMode, setElderMode, resetAccessibility } = useAccessibility()

  return (
    <div>
      <SectionTitle title='适老化' showReset={elderMode} onReset={resetAccessibility} />
      <div className='flex items-center justify-between gap-3 rounded-lg border p-4'>
        <div className='font-medium'>适老化</div>
        <Switch
          checked={elderMode}
          onCheckedChange={setElderMode}
          aria-label='切换适老化模式'
        />
      </div>
    </div>
  )
}

function SectionTitle({
  title,
  showReset = false,
  onReset,
  className,
}: {
  title: string
  showReset?: boolean
  onReset?: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        'mb-2 flex items-center gap-2 text-sm font-semibold text-muted-foreground',
        className
      )}
    >
      {title}
      {showReset && onReset && (
        <Button
          size='icon'
          variant='secondary'
          className='size-4 rounded-full'
          onClick={onReset}
        >
          <RotateCcw className='size-3' />
        </Button>
      )}
    </div>
  )
}

function RadioGroupItem({
  item,
  isTheme = false,
}: {
  item: {
    value: string
    label: string
    icon: (props: SVGProps<SVGSVGElement>) => React.ReactElement
  }
  isTheme?: boolean
}) {
  return (
    <Item
      value={item.value}
      className={cn('group outline-none', 'transition duration-200 ease-in')}
      aria-label={`选择${item.label}`}
      aria-describedby={`${item.value}-description`}
    >
      <div
        className={cn(
          'relative rounded-[6px] ring-[1px] ring-border',
          'group-data-[state=checked]:shadow-2xl group-data-[state=checked]:ring-primary',
          'group-focus-visible:ring-2'
        )}
        role='img'
        aria-hidden='false'
        aria-label={`${item.label}选项预览`}
      >
        <CircleCheck
          className={cn(
            'size-6 fill-primary stroke-white',
            'group-data-[state=unchecked]:hidden',
            'absolute top-0 right-0 translate-x-1/2 -translate-y-1/2'
          )}
          aria-hidden='true'
        />
        <item.icon
          className={cn(
            !isTheme &&
              'fill-primary stroke-primary group-data-[state=unchecked]:fill-muted-foreground group-data-[state=unchecked]:stroke-muted-foreground'
          )}
          aria-hidden='true'
        />
      </div>
      <div
        className='mt-1 text-xs'
        id={`${item.value}-description`}
        aria-live='polite'
      >
        {item.label}
      </div>
    </Item>
  )
}

const fontLabels: Record<(typeof fonts)[number], string> = {
  inter: 'Inter',
  manrope: 'Manrope',
  system: '系统默认',
}

function FontConfig() {
  const { font, setFont, resetFont } = useFont()
  const defaultFont = fonts[0]

  return (
    <div>
      <SectionTitle
        title='字体'
        showReset={font !== defaultFont}
        onReset={resetFont}
      />
      <Select
        value={font}
        onValueChange={(value) => setFont(value as (typeof fonts)[number])}
      >
        <SelectTrigger
          className='w-full max-w-md'
          aria-label='选择界面字体'
          aria-describedby='font-description'
        >
          <SelectValue placeholder='选择字体' />
        </SelectTrigger>
        <SelectContent>
          {fonts.map((item) => (
            <SelectItem key={item} value={item}>
              {fontLabels[item]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div id='font-description' className='sr-only'>
        选择后台界面使用的字体
      </div>
    </div>
  )
}

function ThemeConfig() {
  const { defaultTheme, theme, setTheme } = useTheme()
  return (
    <div>
      <SectionTitle
        title='主题'
        showReset={theme !== defaultTheme}
        onReset={() => setTheme(defaultTheme)}
      />
      <Radio
        value={theme}
        onValueChange={setTheme}
        className='grid w-full max-w-md grid-cols-3 gap-4'
        aria-label='选择主题偏好'
        aria-describedby='theme-description'
      >
        {[
          {
            value: 'system',
            label: '跟随系统',
            icon: IconThemeSystem,
          },
          {
            value: 'light',
            label: '浅色',
            icon: IconThemeLight,
          },
          {
            value: 'dark',
            label: '深色',
            icon: IconThemeDark,
          },
        ].map((item) => (
          <RadioGroupItem key={item.value} item={item} isTheme />
        ))}
      </Radio>
      <div id='theme-description' className='sr-only'>
        可在跟随系统、浅色模式和深色模式之间切换
      </div>
    </div>
  )
}

function SidebarConfig() {
  const { defaultVariant, variant, setVariant } = useLayout()
  return (
    <div className='max-md:hidden'>
      <SectionTitle
        title='侧边栏'
        showReset={defaultVariant !== variant}
        onReset={() => setVariant(defaultVariant)}
      />
      <Radio
        value={variant}
        onValueChange={setVariant}
        className='grid w-full max-w-md grid-cols-3 gap-4'
        aria-label='选择侧边栏样式'
        aria-describedby='sidebar-description'
      >
        {[
          {
            value: 'inset',
            label: '内嵌',
            icon: IconSidebarInset,
          },
          {
            value: 'floating',
            label: '浮动',
            icon: IconSidebarFloating,
          },
          {
            value: 'sidebar',
            label: '标准',
            icon: IconSidebarSidebar,
          },
        ].map((item) => (
          <RadioGroupItem key={item.value} item={item} />
        ))}
      </Radio>
      <div id='sidebar-description' className='sr-only'>
        可在内嵌、浮动和标准侧边栏之间切换
      </div>
    </div>
  )
}

function LayoutConfig() {
  const { open, setOpen } = useSidebar()
  const { defaultCollapsible, collapsible, setCollapsible } = useLayout()

  const radioState = open ? 'default' : collapsible

  return (
    <div className='max-md:hidden'>
      <SectionTitle
        title='布局'
        showReset={radioState !== 'default'}
        onReset={() => {
          setOpen(true)
          setCollapsible(defaultCollapsible)
        }}
      />
      <Radio
        value={radioState}
        onValueChange={(v) => {
          if (v === 'default') {
            setOpen(true)
            return
          }
          setOpen(false)
          setCollapsible(v as Collapsible)
        }}
        className='grid w-full max-w-md grid-cols-3 gap-4'
        aria-label='选择布局样式'
        aria-describedby='layout-description'
      >
        {[
          {
            value: 'default',
            label: '默认',
            icon: IconLayoutDefault,
          },
          {
            value: 'icon',
            label: '紧凑',
            icon: IconLayoutCompact,
          },
          {
            value: 'offcanvas',
            label: '展开',
            icon: IconLayoutFull,
          },
        ].map((item) => (
          <RadioGroupItem key={item.value} item={item} />
        ))}
      </Radio>
      <div id='layout-description' className='sr-only'>
        可在默认展开、紧凑图标和完整展开模式之间切换
      </div>
    </div>
  )
}

function DirConfig() {
  const { defaultDir, dir, setDir } = useDirection()
  return (
    <div>
      <SectionTitle
        title='方向'
        showReset={defaultDir !== dir}
        onReset={() => setDir(defaultDir)}
      />
      <Radio
        value={dir}
        onValueChange={setDir}
        className='grid w-full max-w-md grid-cols-3 gap-4'
        aria-label='选择页面方向'
        aria-describedby='direction-description'
      >
        {[
          {
            value: 'ltr',
            label: '从左到右',
            icon: (props: SVGProps<SVGSVGElement>) => (
              <IconDir dir='ltr' {...props} />
            ),
          },
          {
            value: 'rtl',
            label: '从右到左',
            icon: (props: SVGProps<SVGSVGElement>) => (
              <IconDir dir='rtl' {...props} />
            ),
          },
        ].map((item) => (
          <RadioGroupItem key={item.value} item={item} />
        ))}
      </Radio>
      <div id='direction-description' className='sr-only'>
        可在从左到右和从右到左的页面方向之间切换
      </div>
    </div>
  )
}
