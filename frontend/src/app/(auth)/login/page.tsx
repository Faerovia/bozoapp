"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

const schema = z.object({
  // Email pro běžné uživatele, nebo username (krátký řetězec) pro platform admina.
  email: z.string().min(1, "Zadejte email nebo přihlašovací jméno"),
  password: z.string().min(1, "Heslo je povinné"),
});

type FormData = z.infer<typeof schema>;

export default function LoginPage() {
  // useSearchParams() musí být uvnitř <Suspense> (Next.js 15 CSR bailout rule),
  // jinak build selže při prerender.
  return (
    <Suspense fallback={<Card className="w-full max-w-sm"><CardContent className="py-12" /></Card>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setServerError(null);
    // Backend přijímá email NEBO username. Rozlišíme podle '@'.
    const payload: {
      email?: string;
      username?: string;
      password: string;
    } = data.email.includes("@")
      ? { email: data.email, password: data.password }
      : { username: data.email, password: data.password };
    try {
      await api.post("/auth/login", payload);

      // Default landing podle role + počtu klientů:
      // - platform admin → /admin
      // - OZO s 2+ memberships → /my-clients
      // - jinak → /dashboard
      let next = searchParams.get("next");
      if (!next) {
        try {
          const me = await api.get<{ role: string; is_platform_admin: boolean }>(
            "/auth/me",
          );
          if (me.is_platform_admin) {
            next = "/admin";
          } else if (me.role === "ozo") {
            const memberships = await api.get<{ tenant_id: string }[]>(
              "/auth/memberships"
            );
            next = memberships.length > 1 ? "/my-clients" : "/dashboard";
          } else {
            next = "/dashboard";
          }
        } catch {
          next = "/dashboard";
        }
      }
      router.push(next);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.detail);
      } else {
        setServerError("Chyba připojení k serveru");
      }
    }
  };

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="space-y-1">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-2xl font-bold text-blue-600">OZODigi</span>
        </div>
        <CardTitle>Přihlášení</CardTitle>
        <CardDescription>BOZP a PO management platforma</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email nebo přihlašovací jméno</Label>
            <Input
              id="email"
              type="text"
              placeholder="vas@email.cz"
              autoComplete="username"
              {...register("email")}
            />
            {errors.email && (
              <p className="text-xs text-red-600">{errors.email.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Heslo</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
            />
            {errors.password && (
              <p className="text-xs text-red-600">{errors.password.message}</p>
            )}
          </div>

          {serverError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {serverError}
            </div>
          )}

          <Button type="submit" className="w-full" loading={isSubmitting}>
            Přihlásit se
          </Button>

          <div className="text-center">
            <Link
              href="/forgot-password"
              className="text-sm text-blue-600 hover:underline"
            >
              Zapomenuté heslo?
            </Link>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
