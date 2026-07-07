import { defineCollection, z } from 'astro:content';

const postsCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    date: z.coerce.date().transform((d) => d.toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric'
    })),
    category: z.string().default('PRESS BOX'),
    kind: z.string().optional()
  })
});

export const collections = {
  'posts': postsCollection,
};
