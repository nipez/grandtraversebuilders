/**
 * Force /404 and /404.html to return HTTP 404.
 *
 * Cloudflare Pages serves the static 404.html asset at /404 with status 200
 * (pretty URL), which Search Console flags as a soft 404 / noindex exclusion.
 * Unmatched paths already receive 404.html with status 404 automatically.
 *
 * Note: Pages _redirects only supports 3xx redirects and 200 proxying — a
 * "/404 /404.html 404" rewrite is not supported, so this Function is required.
 */
export async function onRequest(context) {
  const { pathname } = new URL(context.request.url);
  if (pathname !== "/404" && pathname !== "/404.html") {
    return context.next();
  }

  const asset = await context.env.ASSETS.fetch(
    new URL("/404.html", context.request.url)
  );
  const headers = new Headers(asset.headers);
  headers.set("Cache-Control", "no-store");
  headers.set("X-Robots-Tag", "noindex, follow");
  return new Response(asset.body, {
    status: 404,
    statusText: "Not Found",
    headers,
  });
}
