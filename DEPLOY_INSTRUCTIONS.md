# DeathOvers Frontend — Deploy Instructions

## Important: folder placement

Your CrewAI pipeline currently writes articles to `content/posts/*.md` at the
**repo root**. This Astro project expects articles inside
`src/content/posts/*.md` instead (that's Astro's content collections
convention).

You have two options — pick ONE:

### Option 1 (recommended, no pipeline changes needed)
After pushing these frontend files into `deathovers-content`, update your
`app.py` so it writes new articles directly to `src/content/posts/` instead
of `content/posts/`. One-line path change, nothing else in your pipeline
needs to change.

### Option 2 (no app.py changes)
Keep `app.py` writing to `content/posts/` as-is, and instead update
`astro.config.mjs` / `src/content/config.ts` to point the collection at the
root `content/posts/` folder. This needs one extra config tweak — tell me
if you'd rather go this route and I'll adjust the files.

I've built everything assuming **Option 1** since it's the cleaner long-term
setup. Just change the output path in `app.py` from `content/posts/` to
`src/content/posts/`.

## Steps to go live

1. Copy all files from this project into the ROOT of your `deathovers-content`
   repo (so `astro.config.mjs`, `package.json`, `src/`, etc. sit alongside
   your existing `app.py`, `requirements.txt`, `.github/`).
2. Update `app.py`'s output path as described above (Option 1).
3. Delete `src/content/posts/sample-article.md` once you have at least one
   real generated article, or leave it — it'll just show as an extra test
   post until removed.
4. Commit and push to `main`.
5. Go to Vercel → Import `deathovers-content` → it will auto-detect Astro.
   Leave build settings on defaults (Build Command: `astro build`,
   Output: `dist`).
6. Click Deploy. First build takes ~1-2 minutes.
7. Once live, add your custom domain (deathovers.com) under
   Project Settings → Domains.

## Local testing (optional, before pushing)

```
npm install
npm run dev
```

Visit `http://localhost:4321` to preview before deploying.
