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
import { cn } from "@/lib/utils";
import { useTenantContext } from "@/hooks/use-tenant-context";

// ── Schémata ────────────────────────────────────────────────────────────────
const passwordSchema = z.object({
  // Email, osobní číslo nebo username (záleží na subdoméně).
  identifier: z.string().min(1, "Zadejte email, osobní číslo nebo přihlašovací jméno"),
  password: z.string().min(1, "Heslo je povinné"),
});
type PasswordFormData = z.infer<typeof passwordSchema>;

const smsRequestSchema = z.object({
  identifier: z.string().min(3, "Zadejte email, telefon nebo osobní číslo"),
});
type SmsRequestFormData = z.infer<typeof smsRequestSchema>;

const smsVerifySchema = z.object({
  code: z.string().regex(/^\d{6}$/, "Kód musí být 6 číslic"),
});
type SmsVerifyFormData = z.infer<typeof smsVerifySchema>;

type Tab = "password" | "sms";

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
  const [tab, setTab] = useState<Tab>("password");
  const tenant = useTenantContext();

  // Branded login: pokud sub-doména patří tenantu, ukaž název firmy
  // místo generic 'BOZP a PO management platforma'.
  const subtitle = tenant?.name
    ? tenant.name
    : tenant?.isAdmin
    ? "Platform admin"
    : "BOZP a PO management platforma";

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="space-y-1">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-2xl font-bold text-blue-600">DigitalOZO</span>
        </div>
        <CardTitle>Přihlášení</CardTitle>
        <CardDescription>{subtitle}</CardDescription>
      </CardHeader>
      <CardContent>
        {/* Tab switcher */}
        <div className="mb-4 grid grid-cols-2 gap-1 rounded-md bg-gray-100 p-1">
          <button
            type="button"
            onClick={() => setTab("password")}
            className={cn(
              "rounded px-3 py-1.5 text-sm font-medium transition-colors",
              tab === "password"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900",
            )}
          >
            Heslo
          </button>
          <button
            type="button"
            onClick={() => setTab("sms")}
            className={cn(
              "rounded px-3 py-1.5 text-sm font-medium transition-colors",
              tab === "sms"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900",
            )}
          >
            SMS kód
          </button>
        </div>

        {tab === "password" ? <PasswordTab /> : <SmsTab />}
      </CardContent>
    </Card>
  );
}

// ── Heslo tab ────────────────────────────────────────────────────────────────
function PasswordTab() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tenant = useTenantContext();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordFormData>({ resolver: zodResolver(passwordSchema) });

  const onSubmit = async (data: PasswordFormData) => {
    setServerError(null);
    try {
      await api.post("/auth/login", {
        identifier: data.identifier,
        password: data.password,
        tenant_slug: tenant?.slug,
      });
      await redirectAfterLogin(router, searchParams.get("next"));
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.detail);
      } else {
        setServerError("Chyba připojení k serveru");
      }
    }
  };

  // Label se přizpůsobí podle subdoména:
  // - tenant subdomain → "Email nebo osobní číslo"
  // - admin subdomain  → "Přihlašovací jméno"
  // - root             → "Email nebo přihlašovací jméno"
  const idLabel = tenant?.slug && !tenant.isAdmin
    ? "Email nebo osobní číslo"
    : tenant?.isAdmin
    ? "Přihlašovací jméno"
    : "Email nebo přihlašovací jméno";

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="identifier">{idLabel}</Label>
        <Input
          id="identifier"
          type="text"
          placeholder={tenant?.slug && !tenant.isAdmin ? "P1234 nebo vas@email.cz" : "vas@email.cz"}
          autoComplete="username"
          {...register("identifier")}
        />
        {errors.identifier && (
          <p className="text-xs text-red-600">{errors.identifier.message}</p>
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
  );
}

// ── SMS tab ──────────────────────────────────────────────────────────────────
function SmsTab() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tenant = useTenantContext();
  const [stage, setStage] = useState<"request" | "verify">("request");
  const [identifier, setIdentifier] = useState<string>("");
  const [serverError, setServerError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const requestForm = useForm<SmsRequestFormData>({
    resolver: zodResolver(smsRequestSchema),
  });
  const verifyForm = useForm<SmsVerifyFormData>({
    resolver: zodResolver(smsVerifySchema),
  });

  const onRequest = async (data: SmsRequestFormData) => {
    setServerError(null);
    setInfo(null);
    try {
      await api.post("/auth/sms/request", {
        identifier: data.identifier,
        tenant_slug: tenant?.slug,
      });
      setIdentifier(data.identifier);
      setStage("verify");
      setInfo(
        "Pokud účet existuje a má telefon v evidenci zaměstnance, byl odeslán SMS kód. " +
        "V dev režimu zadej kód 111111.",
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.detail);
      } else {
        setServerError("Chyba připojení k serveru");
      }
    }
  };

  const onVerify = async (data: SmsVerifyFormData) => {
    setServerError(null);
    try {
      await api.post("/auth/sms/verify", {
        identifier,
        code: data.code,
        tenant_slug: tenant?.slug,
      });
      await redirectAfterLogin(router, searchParams.get("next"));
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.detail);
      } else {
        setServerError("Chyba připojení k serveru");
      }
    }
  };

  if (stage === "request") {
    return (
      <form onSubmit={requestForm.handleSubmit(onRequest)} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="identifier">Email, telefon nebo přihlašovací jméno</Label>
          <Input
            id="identifier"
            type="text"
            placeholder="vas@email.cz"
            autoComplete="username"
            {...requestForm.register("identifier")}
          />
          {requestForm.formState.errors.identifier && (
            <p className="text-xs text-red-600">
              {requestForm.formState.errors.identifier.message}
            </p>
          )}
          <p className="text-xs text-gray-500">
            Telefon ve formátu +420728319744 nebo email.
          </p>
        </div>

        {serverError && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <Button type="submit" className="w-full" loading={requestForm.formState.isSubmitting}>
          Poslat SMS kód
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={verifyForm.handleSubmit(onVerify)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="code">6-místný kód z SMS</Label>
        <Input
          id="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          placeholder="111111"
          {...verifyForm.register("code")}
        />
        {verifyForm.formState.errors.code && (
          <p className="text-xs text-red-600">
            {verifyForm.formState.errors.code.message}
          </p>
        )}
      </div>

      {info && (
        <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700">
          {info}
        </div>
      )}

      {serverError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {serverError}
        </div>
      )}

      <Button type="submit" className="w-full" loading={verifyForm.formState.isSubmitting}>
        Přihlásit se
      </Button>

      <button
        type="button"
        onClick={() => {
          setStage("request");
          setServerError(null);
          setInfo(null);
        }}
        className="block w-full text-center text-sm text-blue-600 hover:underline"
      >
        Zpět — poslat kód znovu
      </button>
    </form>
  );
}

// ── Routing po loginu (sdílené pro password i SMS) ──────────────────────────
async function redirectAfterLogin(
  router: ReturnType<typeof useRouter>,
  nextParam: string | null,
) {
  // Default landing podle role + počtu klientů:
  // - platform admin → /admin
  // - OZO s 2+ memberships → /my-clients
  // - jinak → /dashboard
  let next = nextParam;
  if (!next) {
    try {
      const me = await api.get<{ role: string; is_platform_admin: boolean }>(
        "/auth/me",
      );
      if (me.is_platform_admin) {
        next = "/admin";
      } else if (me.role === "ozo") {
        const memberships = await api.get<{ tenant_id: string }[]>(
          "/auth/memberships",
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
}
