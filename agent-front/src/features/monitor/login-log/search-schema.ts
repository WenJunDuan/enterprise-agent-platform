import z from 'zod'

export const loginLogSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(10),
  username: z.string().optional().catch(''),
  ipaddr: z.string().optional().catch(''),
  status: z.number().optional(),
  beginTime: z.string().optional().catch(''),
  endTime: z.string().optional().catch(''),
})

export type LoginLogSearchState = z.infer<typeof loginLogSearchSchema>
