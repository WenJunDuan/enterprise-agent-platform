import z from 'zod'

export const userManagementSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(10),
  status: z
    .array(z.union([z.literal('active'), z.literal('inactive')]))
    .optional()
    .catch([]),
  sex: z
    .array(z.union([z.literal('0'), z.literal('1'), z.literal('2')]))
    .optional()
    .catch([]),
  username: z.string().optional().catch(''),
  nickname: z.string().optional().catch(''),
  email: z.string().optional().catch(''),
  phone: z.string().optional().catch(''),
})

export type UserManagementSearchState = z.infer<
  typeof userManagementSearchSchema
>
