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
import { profileDropdownSettingsItems } from '@/components/profile-dropdown-settings-items'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
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

export function ProfileDropdown() {
  const authUser = useAuthStore((state) => state.user)
  const user = buildNavigationUser(authUser)
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useDialogState()
  const [configOpen, setConfigOpen] = useState(false)
  const fallbackText = user.name.slice(0, 1)

  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button variant='ghost' className='relative h-8 w-8 rounded-full'>
            <Avatar className='h-8 w-8'>
              <AvatarImage src={user.avatar} alt={user.name} />
              <AvatarFallback>{fallbackText}</AvatarFallback>
            </Avatar>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className='w-56' align='end' forceMount>
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
