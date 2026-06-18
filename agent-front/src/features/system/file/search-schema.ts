import z from 'zod'

export const fileManagementSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(10),
  originalName: z.string().optional().catch(''),
  extension: z.string().optional().catch(''),
  bizType: z.string().optional().catch(''),
})

export type FileManagementSearchState = z.infer<
  typeof fileManagementSearchSchema
>
