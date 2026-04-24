import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasToken = request.cookies.has("access_token");

  // Nechráněné cesty (login)
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    // Přihlášený uživatel na /login → dashboard
    if (hasToken) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
    return NextResponse.next();
  }

  // Chráněné cesty bez tokenu → login
  if (!hasToken) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Vynech Next.js interní cesty, statické soubory a API proxy
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
