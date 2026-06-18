'use client'

import { type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Box, ChevronRight, Folder } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

export type TreeViewItem = {
  id: string
  name: string
  type: string
  children?: TreeViewItem[]
}

export type TreeViewProps = {
  className?: string
  data: TreeViewItem[]
  selectedId?: string | null
  expandedIds?: Set<string>
  indentation?: number
  onSelect?: (item: TreeViewItem) => void
  onToggleExpand?: (id: string, isOpen: boolean) => void
  getIcon?: (item: TreeViewItem, depth: number, isOpen: boolean) => ReactNode
  renderTrailing?: (
    item: TreeViewItem,
    depth: number,
    isOpen: boolean
  ) => ReactNode
  toggleOnSelect?: boolean
}

type InternalTreeItemProps = {
  item: TreeViewItem
  depth: number
  selectedId?: string | null
  expandedIds: Set<string>
  indentation: number
  onSelect?: (item: TreeViewItem) => void
  onToggleExpand?: (id: string, isOpen: boolean) => void
  getIcon?: (item: TreeViewItem, depth: number, isOpen: boolean) => ReactNode
  renderTrailing?: (
    item: TreeViewItem,
    depth: number,
    isOpen: boolean
  ) => ReactNode
  toggleOnSelect: boolean
}

function renderDefaultIcon(item: TreeViewItem, isOpen: boolean) {
  if (item.children?.length) {
    return (
      <Folder
        className={cn(
          'h-4 w-4 shrink-0 text-primary/80',
          isOpen && 'text-primary'
        )}
      />
    )
  }

  return <Box className='h-4 w-4 shrink-0 text-muted-foreground' />
}

function InternalTreeItem({
  item,
  depth,
  selectedId,
  expandedIds,
  indentation,
  onSelect,
  onToggleExpand,
  getIcon,
  renderTrailing,
  toggleOnSelect,
}: InternalTreeItemProps) {
  const isSelected = selectedId === item.id
  const isOpen = expandedIds.has(item.id)
  const hasChildren = (item.children?.length ?? 0) > 0

  const handleSelect = () => {
    onSelect?.(item)

    if (hasChildren && toggleOnSelect) {
      onToggleExpand?.(item.id, !isOpen)
    }
  }

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={(open) => onToggleExpand?.(item.id, open)}
    >
      <div
        className='relative select-none'
        style={{ paddingLeft: `${depth * indentation}px` }}
      >
        {depth > 0 ? (
          <>
            <span
              aria-hidden='true'
              className='absolute top-0 bottom-0 border-l border-border/70'
              style={{ left: `${indentation / 2}px` }}
            />
            <span
              aria-hidden='true'
              className='absolute top-1/2 h-px w-3 -translate-y-1/2 bg-border/70'
              style={{ left: `${indentation / 2}px` }}
            />
          </>
        ) : null}
        <div
          className={cn(
            'flex min-w-max items-center gap-2 rounded-md px-1 py-0.5 text-[15px] transition-colors',
            'hover:bg-accent/70',
            isSelected && 'bg-primary/10 text-primary'
          )}
        >
          {hasChildren ? (
            <CollapsibleTrigger asChild>
              <Button
                type='button'
                variant='ghost'
                size='icon'
                className='h-6 w-6 shrink-0'
                onClick={(event) => event.stopPropagation()}
              >
                <motion.div
                  initial={false}
                  animate={{ rotate: isOpen ? 90 : 0 }}
                  transition={{ duration: 0.12 }}
                >
                  <ChevronRight className='h-4 w-4' />
                </motion.div>
              </Button>
            </CollapsibleTrigger>
          ) : (
            <span className='h-6 w-6 shrink-0' />
          )}

          {getIcon
            ? getIcon(item, depth, isOpen)
            : renderDefaultIcon(item, isOpen)}

          <button
            type='button'
            className='flex flex-1 items-center gap-2 text-left'
            onClick={handleSelect}
          >
            <span className='whitespace-nowrap'>{item.name}</span>
          </button>

          {renderTrailing?.(item, depth, isOpen)}
        </div>
      </div>

      {hasChildren ? (
        <AnimatePresence initial={false}>
          {isOpen ? (
            <CollapsibleContent forceMount asChild>
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.12 }}
                className='overflow-hidden'
              >
                <div className='space-y-0.5'>
                  {item.children?.map((child) => (
                    <InternalTreeItem
                      key={child.id}
                      item={child}
                      depth={depth + 1}
                      selectedId={selectedId}
                      expandedIds={expandedIds}
                      indentation={indentation}
                      onSelect={onSelect}
                      onToggleExpand={onToggleExpand}
                      getIcon={getIcon}
                      renderTrailing={renderTrailing}
                      toggleOnSelect={toggleOnSelect}
                    />
                  ))}
                </div>
              </motion.div>
            </CollapsibleContent>
          ) : null}
        </AnimatePresence>
      ) : null}
    </Collapsible>
  )
}

export function TreeView({
  className,
  data,
  selectedId,
  expandedIds = new Set(),
  indentation = 20,
  onSelect,
  onToggleExpand,
  getIcon,
  renderTrailing,
  toggleOnSelect = false,
}: TreeViewProps) {
  return (
    <div className={cn('min-w-full w-max space-y-0.5', className)}>
      {data.map((item) => (
        <InternalTreeItem
          key={item.id}
          item={item}
          depth={0}
          selectedId={selectedId}
          expandedIds={expandedIds}
          indentation={indentation}
          onSelect={onSelect}
          onToggleExpand={onToggleExpand}
          getIcon={getIcon}
          renderTrailing={renderTrailing}
          toggleOnSelect={toggleOnSelect}
        />
      ))}
    </div>
  )
}
