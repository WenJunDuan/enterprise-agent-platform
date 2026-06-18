import z from 'zod'

export const operLogSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(10),
  title: z.string().optional().catch(''),
  operName: z.string().optional().catch(''),
  businessType: z.number().optional(),
  status: z.number().optional(),
  beginTime: z.string().optional().catch(''),
  endTime: z.string().optional().catch(''),
})

export type OperLogSearchState = z.infer<typeof operLogSearchSchema>
