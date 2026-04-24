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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const schema = z
  .object({
    new_password: z.string().min(8, "Heslo musí mít alespoň 8 znaků"),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "Hesla se neshodují",
    path: ["confirm_password"],
  });

type FormData = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  // useSearchParams() musí být uvnitř <Suspense> (Next.js 15 CSR bailout rule)
  return (
    <Suspense
      fallback={
        <Card className="w-full max-w-sm">
          <CardContent className="py-12" />
        </Card>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [serverError, setServerError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  // Bez tokenu v URL nemá smysl nic dělat
  if (!token) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Neplatný odkaz</CardTitle>
          <CardDescription>
            Tento odkaz na obnovu hesla je neúplný. Požádejte o nový.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            href="/forgot-password"
            className="text-sm text-blue-600 hover:underline"
          >
            Zpět na zapomenuté heslo
          </Link>
        </CardContent>
      </Card>
    );
  }

  const onSubmit = async (data: FormData) => {
    setServerError(null);
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: data.new_password,
      });
      setSuccess(true);
      // Krátká prodleva, aby uživatel stihl přečíst zprávu
      setTimeout(() => router.push("/login"), 2500);
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(
          err.status === 400
            ? "Odkaz vypršel nebo byl již použit. Požádejte o nový."
            : err.detail
        );
      } else {
        setServerError("Chyba připojení k serveru");
      }
    }
  };

  if (success) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Heslo změněno</CardTitle>
          <CardDescription>
            Přesměrujeme vás na přihlášení…
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="space-y-1">
        <CardTitle>Nové heslo</CardTitle>
        <CardDescription>
          Zadejte nové heslo (min. 8 znaků).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="new_password">Nové heslo</Label>
            <Input
              id="new_password"
              type="password"
              autoComplete="new-password"
              {...register("new_password")}
            />
            {errors.new_password && (
              <p className="text-xs text-red-600">
                {errors.new_password.message}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="confirm_password">Potvrzení hesla</Label>
            <Input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
            {errors.confirm_password && (
              <p className="text-xs text-red-600">
                {errors.confirm_password.message}
              </p>
            )}
          </div>

          {serverError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {serverError}
            </div>
          )}

          <Button type="submit" className="w-full" loading={isSubmitting}>
            Nastavit nové heslo
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
