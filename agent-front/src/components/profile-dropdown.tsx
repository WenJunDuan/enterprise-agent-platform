import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  Check,
  Laptop,
  Moon,
  Settings2,
  Sun,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { buildNavigationUser } from '@/app/navigation/registry'
import { useTheme } from '@/context/theme-provider'
import useDialogState from '@/hooks/use-dialog-state'
import { useAuthStore } from '@/stores/auth-store'
import {
  profileDropdownSettingsItems,
  profileDropdownSystemItems,
} from '@/components/profile-dropdown-settings-items'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { SidebarMenuButton } from '@/components/ui/sidebar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfigDrawer } from '@/components/config-drawer'
import { SignOutDialog } from '@/components/sign-out-dialog'

type ProfileDropdownProps = {
  triggerVariant?: 'header' | 'sidebar'
}

export function ProfileDropdown({
  triggerVariant = 'header',
}: ProfileDropdownProps) {
  const authUser = useAuthStore((state) => state.user)
  const user = buildNavigationUser(authUser)
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useDialogState()
  const [configOpen, setConfigOpen] = useState(false)
  const fallbackText = user.name.slice(0, 1)
  const showSidebarTrigger = triggerVariant === 'sidebar'

  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          {showSidebarTrigger ? (
            <SidebarMenuButton size='lg' className='cursor-pointer'>
              <Avatar className='h-8 w-8 rounded-lg'>
                <AvatarImage src={user.avatar} alt={user.name} />
                <AvatarFallback className='rounded-lg'>
                  {fallbackText}
                </AvatarFallback>
              </Avatar>
              <span className='grid min-w-0 flex-1 text-start text-sm leading-tight'>
                <span className='truncate font-semibold'>{user.name}</span>
                <span className='truncate text-xs'>{user.email}</span>
              </span>
            </SidebarMenuButton>
          ) : (
            <Button
              variant='ghost'
              className='h-10 max-w-56 justify-start gap-2 rounded-md px-2'
            >
              <Avatar className='h-8 w-8'>
                <AvatarImage src={user.avatar} alt={user.name} />
                <AvatarFallback>{fallbackText}</AvatarFallback>
              </Avatar>
              <span className='hidden min-w-0 flex-col items-start gap-0.5 sm:flex'>
                <span className='max-w-36 truncate text-sm leading-none font-medium'>
                  {user.name}
                </span>
                <span className='max-w-36 truncate text-xs leading-none text-muted-foreground'>
                  {user.email}
                </span>
              </span>
            </Button>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent
          className='w-56'
          align={showSidebarTrigger ? 'start' : 'end'}
          side={showSidebarTrigger ? 'right' : 'bottom'}
          forceMount
        >
          <DropdownMenuLabel className='font-normal'>
            <div className='flex flex-col gap-1.5'>
              <p className='text-sm leading-none font-medium'>{user.name}</p>
              <p className='text-xs leading-none text-muted-foreground'>
                {user.email}
              </p>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Sun />
                主题切换
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuItem onSelect={() => setTheme('light')}>
                  <Sun />
                  浅色
                  <Check
                    size={14}
                    className={cn('ms-auto', theme !== 'light' && 'hidden')}
                  />
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setTheme('dark')}>
                  <Moon />
                  深色
                  <Check
                    size={14}
                    className={cn('ms-auto', theme !== 'dark' && 'hidden')}
                  />
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setTheme('system')}>
                  <Laptop />
                  跟随系统
                  <Check
                    size={14}
                    className={cn('ms-auto', theme !== 'system' && 'hidden')}
                  />
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuItem onSelect={() => setConfigOpen(true)}>
              <Settings2 />
              布局设置
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            {profileDropdownSettingsItems.map((item) => {
              const Icon = item.icon

              return (
                <DropdownMenuItem key={item.to} asChild>
                  <Link to={item.to}>
                    <Icon />
                    {item.label}
                  </Link>
                </DropdownMenuItem>
              )
            })}
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Settings2 />
                系统管理
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                {profileDropdownSystemItems.map((item) => {
                  const Icon = item.icon

                  return (
                    <DropdownMenuItem
                      key={`${item.section}-${item.page}`}
                      asChild
                    >
                      <Link
                        to='/$section/$page'
                        params={{ section: item.section, page: item.page }}
                      >
                        <Icon />
                        {item.label}
                      </Link>
                    </DropdownMenuItem>
                  )
                })}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant='destructive' onClick={() => setOpen(true)}>
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <SignOutDialog open={!!open} onOpenChange={setOpen} />
      <ConfigDrawer
        open={!!configOpen}
        onOpenChange={setConfigOpen}
        hideTrigger
      />
    </>
  )
}
