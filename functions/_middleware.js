/**
 * Edge cases Pages _redirects cannot cover cleanly:
 *
 * 1) /404 and /404.html — Pages would serve 404.html at /404 with HTTP 200
 *    (pretty URL). Search Console flags that as a soft 404 / noindex exclusion.
 *    Emit the same body with a real HTTP 404.
 *
 * 2) Template-string leak paths — Google harvested literal paths like
 *    /business/${b.s} from unrendered JS. Those characters are awkward in
 *    _redirects matching, so redirect here (301, single hop) to the best
 *    current equivalent. Keep /404 handling above these redirects.
 *
 * Note: unmatched paths already receive 404.html with status 404 automatically.
 * _redirects still handles .html→extensionless, umlaut slugs, /category, etc.
 */

const TEMPLATE_LEAK_REDIRECTS = new Map([
  ["/business/${b.s}", "/"],
  ["/business/${b.s}.html", "/"],
  ["/business/${sel.slug}", "/"],
  ["/business/${sel.slug}.html", "/"],
  ["/business/${slug}", "/"],
  ["/business/${slug}.html", "/"],
  ["/business/undefined", "/"],
  ["/business/undefined.html", "/"],
  ["/business/null", "/"],
  ["/business/null.html", "/"],
  ["/category/${catSlug}", "/categories"],
  ["/category/${catSlug}.html", "/categories"],
  ["/category/undefined", "/categories"],
  ["/category/undefined.html", "/categories"],
  ["/category/null", "/categories"],
  ["/category/null.html", "/categories"],
]);

function decodePathname(pathname) {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return pathname;
  }
}

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const pathname = url.pathname;
  const decoded = decodePathname(pathname);

  if (pathname === "/404" || pathname === "/404.html") {
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

  const dest =
    TEMPLATE_LEAK_REDIRECTS.get(pathname) ||
    TEMPLATE_LEAK_REDIRECTS.get(decoded);
  if (dest) {
    return Response.redirect(new URL(dest, url.origin).toString(), 301);
  }

  return context.next();
}
