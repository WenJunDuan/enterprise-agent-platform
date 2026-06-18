import { describe, expect, test } from 'bun:test'
import { buildDeptFormDefaults, buildDeptUpdatePayload } from './model'

describe('dept model', () => {
  test('uses the virtual top-level parent when detail parent points to itself', () => {
    expect(
      buildDeptFormDefaults({
        deptId: '100',
        parentId: '100',
        deptName: '顶级部门',
      }).parentId
    ).toBe('0')
  })

  test('does not send current department id as its own parent on update', () => {
    expect(
      buildDeptUpdatePayload(
        {
          parentId: '100',
          deptName: '顶级部门',
          orderNum: '0',
          leader: '管理员',
          phone: '13800138000',
          email: '',
          status: '1',
        },
        '100'
      )
    ).toMatchObject({
      id: '100',
      parentId: '0',
    })
  })
})
