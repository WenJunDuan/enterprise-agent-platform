import { useMemo, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

export type CheckableTreeNode = {
  id: string
  label: string
  children: CheckableTreeNode[]
}

type CheckableTreeProps = {
  nodes: CheckableTreeNode[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  disabled?: boolean
  emptyText?: string
}

function collectAllIds(nodes: CheckableTreeNode[]): string[] {
  return nodes.flatMap((node) => [node.id, ...collectAllIds(node.children)])
}

function getDescendantIds(node: CheckableTreeNode): string[] {
  return [node.id, ...node.children.flatMap(getDescendantIds)]
}

function getAncestorMap(
  nodes: CheckableTreeNode[],
  parent: string | null = null,
  acc: Map<string, string | null> = new Map()
): Map<string, string | null> {
  for (const node of nodes) {
    acc.set(node.id, parent)
    getAncestorMap(node.children, node.id, acc)
  }

  return acc
}

function getNodeMap(
  nodes: CheckableTreeNode[],
  acc: Map<string, CheckableTreeNode> = new Map()
): Map<string, CheckableTreeNode> {
  for (const node of nodes) {
    acc.set(node.id, node)
    getNodeMap(node.children, acc)
  }

  return acc
}

type CheckState = 'checked' | 'unchecked' | 'indeterminate'

function computeCheckState(
  node: CheckableTreeNode,
  selected: Set<string>
): CheckState {
  const descendants = getDescendantIds(node)
  const checkedCount = descendants.filter((id) => selected.has(id)).length

  if (checkedCount === 0) {
    return 'unchecked'
  }

  if (checkedCount === descendants.length) {
    return 'checked'
  }

  return 'indeterminate'
}

export function CheckableTree({
  nodes,
  selectedIds,
  onChange,
  disabled,
  emptyText = '暂无数据。',
}: CheckableTreeProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(
    () => new Set(nodes.map((node) => node.id))
  )

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const ancestorMap = useMemo(() => getAncestorMap(nodes), [nodes])
  const nodeMap = useMemo(() => getNodeMap(nodes), [nodes])

  function setChecked(node: CheckableTreeNode, checked: boolean) {
    const next = new Set(selectedSet)
    const descendants = getDescendantIds(node)

    if (checked) {
      descendants.forEach((id) => next.add(id))
    } else {
      descendants.forEach((id) => next.delete(id))
    }

    let cursorId: string | null = ancestorMap.get(node.id) ?? null
    while (cursorId) {
      const ancestor = nodeMap.get(cursorId)
      if (!ancestor) {
        break
      }

      const allSelected = ancestor.children.every((child) =>
        getDescendantIds(child).every((id) => next.has(id))
      )

      if (allSelected) {
        next.add(ancestor.id)
      } else {
        next.delete(ancestor.id)
      }

      cursorId = ancestorMap.get(cursorId) ?? null
    }

    onChange(Array.from(next))
  }

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  function renderNode(node: CheckableTreeNode, depth: number) {
    const state = computeCheckState(node, selectedSet)
    const hasChildren = node.children.length > 0
    const isOpen = expandedIds.has(node.id)
    const checkedValue =
      state === 'checked'
        ? true
        : state === 'indeterminate'
          ? 'indeterminate'
          : false

    return (
      <div key={node.id} className='select-none'>
        <div
          className={cn(
            'flex items-center gap-1 rounded-md px-1 py-1 text-sm',
            'hover:bg-accent/60'
          )}
          style={{ paddingLeft: `${depth * 16 + 4}px` }}
        >
          {hasChildren ? (
            <Button
              type='button'
              variant='ghost'
              size='icon'
              className='h-6 w-6 shrink-0'
              onClick={() => toggleExpand(node.id)}
            >
              <ChevronRight
                className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-90')}
              />
            </Button>
          ) : (
            <span className='h-6 w-6 shrink-0' />
          )}
          <Checkbox
            checked={checkedValue}
            disabled={disabled}
            onCheckedChange={(value) => {
              setChecked(node, value === true)
            }}
            className='translate-y-[1px]'
            aria-label={`选中 ${node.label}`}
          />
          <span className='truncate'>{node.label}</span>
        </div>

        {hasChildren && isOpen ? (
          <div>{node.children.map((child) => renderNode(child, depth + 1))}</div>
        ) : null}
      </div>
    )
  }

  function selectAll() {
    onChange(collectAllIds(nodes))
  }

  function clearAll() {
    onChange([])
  }

  function expandAll() {
    setExpandedIds(new Set(collectAllIds(nodes)))
  }

  function collapseAll() {
    setExpandedIds(new Set())
  }

  return (
    <div className='flex flex-col gap-2'>
      <div className='flex flex-wrap gap-2'>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={selectAll}
          disabled={disabled || nodes.length === 0}
        >
          全选
        </Button>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={clearAll}
          disabled={disabled || selectedIds.length === 0}
        >
          全不选
        </Button>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={expandAll}
          disabled={nodes.length === 0}
        >
          展开全部
        </Button>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={collapseAll}
          disabled={expandedIds.size === 0}
        >
          折叠全部
        </Button>
      </div>

      <div className='no-scrollbar max-h-72 overflow-auto rounded-md border bg-background p-1'>
        {nodes.length === 0 ? (
          <div className='flex h-24 items-center justify-center text-sm text-muted-foreground'>
            {emptyText}
          </div>
        ) : (
          nodes.map((node) => renderNode(node, 0))
        )}
      </div>
    </div>
  )
}
