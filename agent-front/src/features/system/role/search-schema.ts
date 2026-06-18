import z from 'zod'

export const roleManagementSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(10),
  roleName: z.string().optional().catch(''),
  roleKey: z.string().optional().catch(''),
  status: z
    .array(z.union([z.literal('active'), z.literal('inactive')]))
    .optional()
    .catch([]),
})

export type RoleManagementSearchState = z.infer<
  typeof roleManagementSearchSchema
>
