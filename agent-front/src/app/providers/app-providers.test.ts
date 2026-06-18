import { describe, expect, test } from 'bun:test'
import { QueryClient } from '@tanstack/react-query'
import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { SearchProvider } from '@/context/search-provider'
import { Route as RootRoute } from '@/routes/__root'
import { AppProviders } from './app-providers'

type ElementWithChildren = ReactElement<{ children?: ReactNode }>

function containsElementType(node: ReactNode, expectedType: unknown): boolean {
  if (Array.isArray(node)) {
    return node.some((child) => containsElementType(child, expectedType))
  }

  if (!isValidElement(node)) {
    return false
  }

  const element = node as ElementWithChildren
  if (element.type === expectedType) {
    return true
  }

  return containsElementType(element.props.children, expectedType)
}

describe('app provider topology', () => {
  test('keeps SearchProvider out of AppProviders because it uses router hooks', () => {
    const element = AppProviders({
      children: null,
      queryClient: new QueryClient(),
    })

    expect(containsElementType(element, SearchProvider)).toBe(false)
  })

  test('mounts SearchProvider from the root route inside RouterProvider context', () => {
    const RootComponent = RootRoute.options.component as () => ReactNode

    expect(containsElementType(RootComponent(), SearchProvider)).toBe(true)
  })
})
