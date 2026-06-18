import { Link } from '@tanstack/react-router'
import { APP_TITLE } from '@/config/app'
import { Logo } from '@/assets/logo'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'

export function AppTitle() {
  const { setOpenMobile } = useSidebar()
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          size='lg'
          className='px-2 hover:bg-transparent active:bg-transparent'
          asChild
        >
          <Link
            to='/'
            onClick={() => setOpenMobile(false)}
            className='flex flex-1 items-center gap-2 text-start leading-tight group-data-[collapsible=icon]:justify-center'
          >
            <Logo className='size-5 shrink-0' title={APP_TITLE} />
            <span className='truncate text-[25px] leading-none font-semibold group-data-[collapsible=icon]:hidden'>
              {APP_TITLE}
            </span>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
