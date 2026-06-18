'use client'

import { useMemo, useState } from 'react'
import { DynamicIcon, type IconName } from 'lucide-react/dynamic'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { FormControl } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'

type IconPreset = {
  name: IconName
  label: string
}

const ICON_PRESET_NAMES: IconName[] = [
  'layout-dashboard',
  'layout-grid',
  'blocks',
  'house',
  'app-window',
  'panel-left',
  'panels-top-left',
  'panel-right-open',
  'list-tree',
  'menu',
  'table',
  'table-properties',
  'table-cells-split',
  'folder',
  'folder-open',
  'folder-plus',
  'folder-tree',
  'files',
  'file-text',
  'file-cog',
  'file-check',
  'file-chart-column-increasing',
  'book-open-text',
  'book-marked',
  'book-user',
  'notebook-pen',
  'clipboard-list',
  'clipboard-check',
  'briefcase-business',
  'building-2',
  'map-pinned',
  'users',
  'users-round',
  'user-round',
  'circle-user-round',
  'user-plus',
  'user-check',
  'user-pen',
  'user-x',
  'user-cog',
  'contact-round',
  'id-card',
  'shield',
  'shield-check',
  'shield-off',
  'shield-alert',
  'key-round',
  'lock',
  'lock-keyhole',
  'fingerprint',
  'badge-check',
  'badge-alert',
  'badge-info',
  'settings',
  'settings-2',
  'wrench',
  'tool-case',
  'sliders-horizontal',
  'pencil',
  'pencil-line',
  'eraser',
  'search',
  'filter',
  'funnel',
  'rotate-ccw',
  'refresh-cw',
  'history',
  'undo-2',
  'redo-2',
  'monitor-cog',
  'monitor-check',
  'laptop',
  'computer',
  'server',
  'database',
  'database-zap',
  'database-backup',
  'hard-drive',
  'network',
  'git-branch',
  'workflow',
  'chart-network',
  'calendar',
  'calendar-clock',
  'calendar-check',
  'calendar-range',
  'clock-3',
  'timer',
  'mail',
  'mail-check',
  'send',
  'phone',
  'phone-call',
  'map-pin',
  'navigation',
  'bell',
  'bell-ring',
  'message-square',
  'messages-square',
  'logs',
  'scroll-text',
  'receipt-text',
  'alert-triangle',
  'circle-help',
  'info',
  'circle-alert',
  'octagon-alert',
  'bug',
  'bug-play',
]

const ICON_LABEL_OVERRIDES: Partial<Record<IconName, string>> = {
  'layout-dashboard': '仪表盘',
  'layout-grid': '布局面板',
  blocks: '功能模块',
  house: '系统首页',
  'app-window': '页面组件',
  'list-tree': '树形菜单',
  menu: '菜单按钮',
  folder: '目录',
  'folder-open': '打开目录',
  'folder-plus': '新增目录',
  'folder-tree': '目录树',
  files: '文件管理',
  'file-text': '文本文件',
  'book-open-text': '字典文档',
  'briefcase-business': '岗位业务',
  'building-2': '组织架构',
  users: '用户集合',
  'users-round': '角色集合',
  'user-round': '单用户',
  'circle-user-round': '用户中心',
  'user-plus': '新增用户',
  'user-check': '用户启用',
  'user-pen': '用户编辑',
  'user-x': '用户停用',
  shield: '权限盾牌',
  'shield-check': '权限通过',
  'shield-off': '权限禁用',
  'shield-alert': '权限告警',
  'key-round': '密钥安全',
  settings: '系统设置',
  'settings-2': '高级设置',
  wrench: '维护工具',
  'monitor-cog': '监控配置',
  network: '网络拓扑',
  database: '数据库',
  'database-zap': '缓存数据库',
  calendar: '日历计划',
  'calendar-clock': '定时任务',
  mail: '消息通知',
  phone: '联系方式',
  'map-pin': '地理位置',
  logs: '日志审计',
  'alert-triangle': '风险告警',
  'circle-help': '帮助说明',
}

function formatIconLabel(name: IconName) {
  return name
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

const ICON_PRESETS: IconPreset[] = ICON_PRESET_NAMES.map((name) => ({
  name,
  label: ICON_LABEL_OVERRIDES[name] ?? formatIconLabel(name),
}))

type MenuIconPickerProps = {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

function normalizeKeyword(value: string) {
  return value.trim().toLowerCase()
}

export function MenuIconPicker({ value, onChange, disabled }: MenuIconPickerProps) {
  const [open, setOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const normalizedKeyword = normalizeKeyword(keyword)

  const selectedPreset = useMemo(
    () => ICON_PRESETS.find((item) => item.name === value),
    [value]
  )

  const filteredPresets = useMemo(() => {
    if (!normalizedKeyword) {
      return ICON_PRESETS
    }

    return ICON_PRESETS.filter((item) => {
      const searchText = `${item.name} ${item.label}`.toLowerCase()
      return searchText.includes(normalizedKeyword)
    })
  }, [normalizedKeyword])

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen)

        if (!nextOpen) {
          setKeyword('')
        }
      }}
    >
      <PopoverTrigger asChild>
        <FormControl>
          <Button
            type='button'
            variant='outline'
            role='combobox'
            disabled={disabled}
            className={cn(
              'w-full justify-between font-normal',
              !value && 'text-muted-foreground'
            )}
          >
            <span className='flex min-w-0 items-center gap-2'>
              {selectedPreset ? (
                <DynamicIcon
                  name={selectedPreset.name}
                  className='size-4 shrink-0'
                />
              ) : null}
              <span className='truncate'>
                {selectedPreset ? selectedPreset.label : '请选择图标'}
              </span>
            </span>
            <span className='text-xs text-muted-foreground'>
              {selectedPreset?.name ?? '无'}
            </span>
          </Button>
        </FormControl>
      </PopoverTrigger>

      <PopoverContent className='w-[420px] p-0' align='start'>
        <div className='border-b p-3'>
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder='搜索图标名称'
          />
        </div>

        <div className='flex items-center justify-between border-b px-3 py-2'>
          <span className='text-xs text-muted-foreground'>
            共 {filteredPresets.length} 个可选图标
          </span>
          <Button
            type='button'
            variant='ghost'
            size='sm'
            disabled={disabled || !value}
            onClick={() => {
              onChange('')
              setOpen(false)
            }}
          >
            清除
          </Button>
        </div>

        <ScrollArea className='h-[320px]'>
          {filteredPresets.length > 0 ? (
            <div className='grid grid-cols-4 gap-2 p-3'>
              {filteredPresets.map((item) => {
                const isSelected = item.name === value

                return (
                  <button
                    key={item.name}
                    type='button'
                    className={cn(
                      'flex flex-col items-center gap-1 rounded-md border px-2 py-2 text-xs transition-colors hover:bg-accent/70',
                      isSelected && 'border-primary bg-primary/10 text-primary'
                    )}
                    onClick={() => {
                      onChange(item.name)
                      setOpen(false)
                    }}
                  >
                    <DynamicIcon name={item.name} className='size-4 shrink-0' />
                    <span className='line-clamp-1 text-[11px]'>{item.label}</span>
                    <span className='line-clamp-1 text-[10px] text-muted-foreground'>
                      {item.name}
                    </span>
                  </button>
                )}
              )}
            </div>
          ) : (
            <div className='flex h-24 items-center justify-center text-sm text-muted-foreground'>
              未找到匹配的图标。
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
