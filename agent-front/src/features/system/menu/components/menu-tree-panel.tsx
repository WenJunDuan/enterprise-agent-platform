'use client'

import { Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardHeader,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { TreeView } from '@/components/ui/tree-view'
import { SelectDropdown } from '@/components/select-dropdown'
import {
  buildMenuTreeViewItems,
  filterMenuTree,
  findMenuById,
  type MenuTreeNode,
  type MenuType,
  type MenuTypeFilter,
} from '../model'

type MenuTreePanelProps = {
  tree: MenuTreeNode[]
  isPending: boolean
  selectedMenuId: string | null
  expandedMenuIds: Set<string>
  keyword: string
  typeFilter: MenuTypeFilter
  onKeywordChange: (value: string) => void
  onTypeFilterChange: (value: MenuTypeFilter) => void
  onSelectMenu: (menuId: string) => void
  onDeleteMenu: (menuId: string) => void
  onToggleExpand: (menuId: string, isOpen: boolean) => void
}

function getMenuTypeMeta(menuType: MenuType) {
  if (menuType === 'F') {
    return {
      label: '按钮',
      className: 'border-amber-300 bg-amber-100 text-amber-700',
    }
  }

  if (menuType === 'C') {
    return {
      label: '菜单',
      className: 'border-blue-300 bg-blue-100 text-blue-700',
    }
  }

  return {
    label: '目录',
    className: 'border-emerald-300 bg-emerald-100 text-emerald-700',
  }
}

export function MenuTreePanel({
  tree,
  isPending,
  selectedMenuId,
  expandedMenuIds,
  keyword,
  typeFilter,
  onKeywordChange,
  onTypeFilterChange,
  onSelectMenu,
  onDeleteMenu,
  onToggleExpand,
}: MenuTreePanelProps) {
  const filteredTree = filterMenuTree(tree, keyword, typeFilter)
  const treeViewItems = buildMenuTreeViewItems(filteredTree)

  return (
    <Card className='h-full overflow-hidden py-0'>
      <CardHeader className='border-b px-4 py-3'>
        <div className='grid min-h-10 grid-cols-[minmax(0,1fr)_100px] items-center gap-3'>
          <Input
            value={keyword}
            onChange={(event) => onKeywordChange(event.target.value)}
            placeholder='搜索菜单名称'
          />
          <SelectDropdown
            isControlled
            value={typeFilter}
            onValueChange={(value) => onTypeFilterChange(value as MenuTypeFilter)}
            withFormControl={false}
            items={[
              { label: '全部类型', value: 'all' },
              { label: '目录', value: 'M' },
              { label: '菜单', value: 'C' },
              { label: '按钮', value: 'F' },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent className='space-y-2 px-3 pt-1 pb-2'>
        <div className='no-scrollbar h-[calc(100vh-21rem)] min-h-[24rem] overflow-auto p-1'>
          {isPending ? (
            <div className='space-y-3'>
              <Skeleton className='h-16 w-full' />
              <Skeleton className='h-16 w-[92%]' />
              <Skeleton className='h-16 w-[84%]' />
            </div>
          ) : filteredTree.length > 0 ? (
            <TreeView
              data={treeViewItems}
              selectedId={selectedMenuId}
              expandedIds={expandedMenuIds}
              indentation={20}
              toggleOnSelect
              onSelect={(item) => onSelectMenu(item.id)}
              onToggleExpand={onToggleExpand}
              renderTrailing={(item) => {
                const node =
                  findMenuById(filteredTree, item.id) ?? findMenuById(tree, item.id)

                if (!node) {
                  return null
                }

                const typeMeta = getMenuTypeMeta(node.menuType)

                return (
                  <div className='group flex items-center gap-1.5'>
                    <Badge
                      variant='outline'
                      className={`pointer-events-none h-5 px-1.5 text-[10px] ${typeMeta.className}`}
                    >
                      {typeMeta.label}
                    </Badge>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      className='size-6 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive'
                      onClick={(event) => {
                        event.stopPropagation()
                        onDeleteMenu(item.id)
                      }}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                )
              }}
            />
          ) : (
            <div className='flex h-40 items-center justify-center text-sm text-muted-foreground'>
              未匹配到菜单数据。
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
