'use client'

import { useState } from 'react'
import { Check, ChevronsUpDown, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { FormControl } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { TreeView } from '@/components/ui/tree-view'
import {
  buildDeptTreeViewItems,
  createDefaultExpandedDeptIds,
  ensureDeptPathExpanded,
  filterDeptTree,
  findDeptById,
  getDeptRootLabel,
  type DeptTreeNode,
} from '../model'

type DeptParentPickerProps = {
  value: string
  onChange: (value: string) => void
  nodes: DeptTreeNode[]
  excludedIds: Set<string>
  disabled?: boolean
}

function filterExcludedNodes(
  nodes: DeptTreeNode[],
  excludedIds: Set<string>
): DeptTreeNode[] {
  return nodes.flatMap((node) => {
    if (excludedIds.has(node.deptId)) {
      return []
    }

    return [
      {
        ...node,
        children: filterExcludedNodes(node.children ?? [], excludedIds),
      },
    ]
  })
}

function collectExpandableIds(nodes: DeptTreeNode[]) {
  const ids = new Set<string>()

  function visit(branch: DeptTreeNode[]) {
    branch.forEach((node) => {
      if ((node.children?.length ?? 0) > 0) {
        ids.add(node.deptId)
        visit(node.children ?? [])
      }
    })
  }

  visit(nodes)
  return ids
}

export function DeptParentPicker({
  value,
  onChange,
  nodes,
  excludedIds,
  disabled,
}: DeptParentPickerProps) {
  const [open, setOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  const availableNodes = filterExcludedNodes(nodes, excludedIds)
  const filteredNodes = filterDeptTree(availableNodes, keyword)
  const treeViewItems = buildDeptTreeViewItems(filteredNodes)
  const defaultExpandedIds = keyword.trim()
    ? collectExpandableIds(filteredNodes)
    : createDefaultExpandedDeptIds(availableNodes)
  const effectiveExpandedIds = ensureDeptPathExpanded(
    new Set([...defaultExpandedIds, ...expandedIds]),
    keyword.trim() ? filteredNodes : availableNodes,
    value || null
  )
  const selectedLabel =
    value === '0'
      ? getDeptRootLabel(availableNodes)
      : (findDeptById(availableNodes, value)?.deptName ?? '请选择上级部门')

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
            <span className='truncate'>{selectedLabel}</span>
            <ChevronsUpDown className='ml-2 size-4 shrink-0 opacity-50' />
          </Button>
        </FormControl>
      </PopoverTrigger>

      <PopoverContent className='w-[360px] p-0' align='start'>
        <div className='border-b p-3'>
          <div className='relative'>
            <Search className='absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder='搜索上级部门'
              className='pl-9'
            />
          </div>
        </div>

        <div className='no-scrollbar max-h-[320px] overflow-auto p-2'>
          <button
            type='button'
            className={cn(
              'mb-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent/70',
              value === '0' && 'bg-primary/10 text-primary'
            )}
            onClick={() => {
              onChange('0')
              setOpen(false)
            }}
          >
            <Check
              className={cn(
                'size-4 shrink-0',
                value === '0' ? 'opacity-100' : 'opacity-0'
              )}
            />
            <span>顶级部门</span>
          </button>

          {filteredNodes.length > 0 ? (
            <TreeView
              data={treeViewItems}
              selectedId={value}
              expandedIds={effectiveExpandedIds}
              indentation={18}
              onSelect={(item) => {
                onChange(item.id)
                setOpen(false)
              }}
              onToggleExpand={(deptId, isOpen) => {
                setExpandedIds((prev) => {
                  const next = new Set(prev)

                  if (isOpen) {
                    next.add(deptId)
                  } else {
                    next.delete(deptId)
                  }

                  return next
                })
              }}
            />
          ) : (
            <div className='px-3 py-6 text-center text-sm text-muted-foreground'>
              未找到匹配的部门。
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
