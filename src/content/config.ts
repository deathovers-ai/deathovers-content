import { defineCollection, z } from 'astro:content';

const posts = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    date: z.coerce.date().optional(),
    category: z.enum(['press-box', 'tactical-sheets', 'simulations']),
    targetEntity: z.string().optional(),
    metricFocus: z.string().optional(),
    confidenceScore: z.number().optional(),
    draft: z.boolean().optional().default(false)
  })
});

export const collections = { posts };
