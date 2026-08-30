/** @type {import('next').NextConfig} */
// Static export: the site is numbers baked at build time, so it deploys to any
// static host (GitHub Pages, Vercel) with no server and nothing to keep running.
export default { output: "export", images: { unoptimized: true } };
