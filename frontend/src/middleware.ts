import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login"];

/**
 * Extrahuje tenant slug ze subdomény. Pro Host = 'strojirny-abc.localhost:3000'
 * a base = '.localhost' vrátí 'strojirny-abc'.
 *
 * RESERVED subdomains ('admin', 'www', 'api', 'app') vrátíme s flagem
 * is_reserved aby route handlery věděly o speciálním kontextu.
 */
const RESERVED = new Set(["admin", "www", "api", "app", "static", "cdn"]);

function extractSlug(host: string | null, base: string): { slug: string | null; reserved: boolean } {
  if (!host) return { slug: null, reserved: false };
  const h = host.split(":")[0].toLowerCase();
  const b = base.startsWith(".") ? base : "." + base;
  const baseStripped = b.slice(1);
  if (!h.endsWith(baseStripped)) return { slug: null, reserved: false };
  const prefix = h.slice(0, -baseStripped.length).replace(/\.$/, "");
  if (!prefix) return { slug: null, reserved: false };
  const slug = prefix.split(".")[0];
  return { slug, reserved: RESERVED.has(slug) };
}

const BASE_DOMAIN = process.env.NEXT_PUBLIC_BASE_DOMAIN || ".localhost";

export function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;
  const hasToken = request.cookies.has("access_token");
  const isLogoutFlow = pathname.startsWith("/login") && searchParams.get("logout") === "1";

  // Subdomain → forward jako request header pro server components/API.
  const host = request.headers.get("host");
  const { slug, reserved } = extractSlug(host, BASE_DOMAIN);
  const requestHeaders = new Headers(request.headers);
  if (slug) requestHeaders.set("x-tenant-slug", slug);
  if (reserved) requestHeaders.set("x-tenant-reserved", "1");

  // Nechráněné cesty (login)
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    if (hasToken && !isLogoutFlow) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  // Chráněné cesty bez tokenu → login
  if (!hasToken) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  // Vynech Next.js interní cesty, statické soubory a API proxy
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
