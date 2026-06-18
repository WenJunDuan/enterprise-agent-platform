const defaultColumnLabels: Record<string, string> = {
  id: '编号',
  title: '标题',
  status: '状态',
  priority: '优先级',
  username: '用户名',
  nickname: '昵称',
  deptName: '部门名称',
  fullName: '姓名',
  email: '邮箱',
  phone: '手机号',
  phoneNumber: '手机号',
  sex: '性别',
  role: '角色',
  loginDate: '最近登录',
  createTime: '创建时间',
  remark: '备注',
}

export function getColumnToggleLabel(columnId: string, labelFromMeta?: string) {
  return labelFromMeta ?? defaultColumnLabels[columnId] ?? columnId
}
