"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api } from "@/lib/api";
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

const schema = z.object({
  email: z.string().email("Zadejte platný email"),
});

type FormData = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  // Stav `submitted` schováme formulář a ukážeme potvrzení — nezávisle na tom,
  // zda email existuje. Backend vrací vždy 204 kvůli enumeration resistance,
  // takže i UI se chová stejně pro existující/neexistující email.
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setServerError(null);
    try {
      await api.post("/auth/forgot-password", data);
      setSubmitted(true);
    } catch {
      // 429 (rate limit) nebo 5xx — zobraz generickou chybu
      setServerError("Nepodařilo se odeslat požadavek. Zkuste to za chvíli.");
    }
  };

  if (submitted) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle>Zkontrolujte email</CardTitle>
          <CardDescription>
            Pokud je email registrovaný, odeslali jsme na něj odkaz pro
            obnovení hesla. Platnost odkazu je 1 hodina.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            href="/login"
            className="text-sm text-blue-600 hover:underline"
          >
            Zpět na přihlášení
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="space-y-1">
        <CardTitle>Zapomenuté heslo</CardTitle>
        <CardDescription>
          Zadejte email a my vám pošleme odkaz pro obnovení.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="vas@email.cz"
              autoComplete="email"
              {...register("email")}
            />
            {errors.email && (
              <p className="text-xs text-red-600">{errors.email.message}</p>
            )}
          </div>

          {serverError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {serverError}
            </div>
          )}

          <Button type="submit" className="w-full" loading={isSubmitting}>
            Odeslat odkaz
          </Button>

          <div className="text-center">
            <Link
              href="/login"
              className="text-sm text-blue-600 hover:underline"
            >
              Zpět na přihlášení
            </Link>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
