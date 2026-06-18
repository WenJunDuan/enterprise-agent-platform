import z from 'zod'

export const dynamicPageSearchSchema = z.record(z.string(), z.unknown()).catch({})
