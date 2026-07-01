import { defineCollection, z } from 'astro:content';

const posts = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    category: z.enum(['press-box', 'tactical-sheets', 'simulations']),
    date: z.coerce.date().optional(),
    excerpt: z.string().optional(),
    match: z.string().optional(),
    teams: z.array(z.string()).optional(),
    tags: z.array(z.string()).optional(),
    draft: z.boolean().optional().default(false)
  })
});

export const collections = { posts };
