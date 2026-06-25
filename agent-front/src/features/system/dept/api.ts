import { toId } from '@/lib/ids'
import {
  filterDeptTree,
  type DeptDetail,
  type DeptFormInput,
  type DeptListSearch,
  type DeptTreeNode,
} from './model'

const localDeptTree: DeptTreeNode[] = [
  {
    deptId: '100',
    parentId: '0',
    deptName: '管理中心',
    orderNum: 0,
    leader: '系统管理员',
    phone: '13800000000',
    email: 'admin@example.com',
    status: 1,
    createTime: '2026-06-25 00:00:00',
    children: [
      {
        deptId: '101',
        parentId: '100',
        deptName: '评审部',
        orderNum: 1,
        leader: '评审人员',
        phone: '13900000000',
        email: 'reviewer@example.com',
        status: 1,
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
    ],
  },
]

function flattenDeptTree(nodes: DeptTreeNode[]) {
  const result: DeptTreeNode[] = []

  function visit(node: DeptTreeNode) {
    result.push(node)
    node.children.forEach(visit)
  }

  nodes.forEach(visit)
  return result
}

function filterByStatus(
  nodes: DeptTreeNode[],
  status?: 'active' | 'inactive'
): DeptTreeNode[] {
  if (!status) {
    return nodes
  }

  const statusValue = status === 'active' ? 1 : 0

  return nodes.flatMap((node) => {
    const children: DeptTreeNode[] = filterByStatus(node.children, status)
    if (node.status === statusValue || children.length > 0) {
      return [{ ...node, children }]
    }

    return []
  })
}

export async function fetchDeptList(search?: Partial<DeptListSearch>) {
  const status = search?.status === 'all' ? undefined : search?.status

  return filterByStatus(
    filterDeptTree(localDeptTree, search?.deptName ?? ''),
    status
  )
}

export async function fetchDeptDetail(deptId: string) {
  return (flattenDeptTree(localDeptTree).find((dept) => dept.deptId === deptId) ??
    localDeptTree[0]) as DeptDetail
}

export async function createDept(_input: DeptFormInput) {
  return String(flattenDeptTree(localDeptTree).length + 100)
}

export async function updateDept(_input: DeptFormInput, _id: string) {
  return null
}

export async function deleteDept(id: string) {
  return toId(id) ? null : null
}
