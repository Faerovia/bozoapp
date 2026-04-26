"use client";

/**
 * Univerzální dialog pro digitální podpis zaměstnance.
 *
 * Použití:
 *   <SignatureDialog
 *     open={open}
 *     onClose={() => setOpen(false)}
 *     docType="oopp_issue"
 *     docId={issue.id}
 *     employeeId={issue.employee_id}
 *     employeeName={issue.employee_name}
 *     hasLoginAccount={true}  // false → forced SMS-only
 *     onSigned={(signature) => { ...attach to doc... }}
 *   />
 *
 * Flow:
 * 1. Uživatel vybere auth_method: "password" nebo "sms_otp" (radio).
 * 2. Klik na "Pokračovat" → POST /signatures/initiate.
 *    - Pro sms_otp se odešle SMS (v dev mode mock = 111111).
 *    - Pro password se jen otevře input pro heslo.
 * 3. Zadá heslo nebo SMS kód → POST /signatures/verify.
 * 4. Po úspěchu callback onSigned(signature) — caller si zařídí
 *    attach (např. /oopp/issues/{id}/attach-signature).
 */

import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { ShieldCheck, KeyRound, Smartphone, AlertCircle, CheckCircle2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  SignatureDocType,
  SignatureAuthMethod,
  SignatureRecord,
  SignatureInitiateResponse,
} from "@/types/api";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface SignatureDialogProps {
  open: boolean;
  onClose: () => void;
  docType: SignatureDocType;
  docId: string;
  employeeId: string;
  employeeName: string;
  /** Pokud false, je možný jen sms_otp (zaměstnanec nemá login). */
  hasLoginAccount: boolean;
  /** Volá se po úspěšném vytvoření podpisu — caller ho přilepí k dokumentu. */
  onSigned: (signature: SignatureRecord) => void;
  /** Custom title — default "Digitální podpis". */
  title?: string;
}

type Step = "choose" | "code" | "password";

export function SignatureDialog({
  open,
  onClose,
  docType,
  docId,
  employeeId,
  employeeName,
  hasLoginAccount,
  onSigned,
  title = "Digitální podpis",
}: SignatureDialogProps) {
  const [step, setStep] = useState<Step>("choose");
  const [authMethod, setAuthMethod] = useState<SignatureAuthMethod>(
    hasLoginAccount ? "password" : "sms_otp"
  );
  const [codeOrPassword, setCodeOrPassword] = useState("");
  const [smsInfo, setSmsInfo] = useState<SignatureInitiateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setStep("choose");
      setAuthMethod(hasLoginAccount ? "password" : "sms_otp");
      setCodeOrPassword("");
      setSmsInfo(null);
      setError(null);
    }
  }, [open, hasLoginAccount]);

  const initiateMut = useMutation({
    mutationFn: (m: SignatureAuthMethod) =>
      api.post<SignatureInitiateResponse>("/signatures/initiate", {
        doc_type: docType,
        doc_id: docId,
        employee_id: employeeId,
        auth_method: m,
      }),
    onSuccess: (resp, m) => {
      setSmsInfo(resp);
      setStep(m === "sms_otp" ? "code" : "password");
      setError(null);
    },
    onError: (e: unknown) => {
      setError(e instanceof ApiError ? e.detail : "Chyba serveru");
    },
  });

  const verifyMut = useMutation({
    mutationFn: () =>
      api.post<SignatureRecord>("/signatures/verify", {
        doc_type: docType,
        doc_id: docId,
        employee_id: employeeId,
        auth_method: authMethod,
        code_or_password: codeOrPassword,
      }),
    onSuccess: (sig) => {
      onSigned(sig);
    },
    onError: (e: unknown) => {
      setError(e instanceof ApiError ? e.detail : "Chyba serveru");
    },
  });

  return (
    <Dialog open={open} onClose={onClose} title={title} size="md">
      <div className="space-y-4">
        {/* Identita zaměstnance — pevně, nelze přepsat */}
        <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 px-3 py-2 flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-blue-600 dark:text-blue-300 shrink-0" />
          <div className="text-sm">
            <span className="text-gray-500 dark:text-gray-400">Podepisuje: </span>
            <strong className="text-gray-900 dark:text-gray-100">{employeeName}</strong>
          </div>
        </div>

        {step === "choose" && (
          <>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Zvolte způsob ověření identity. Po úspěšném ověření bude podpis
              uložen do nezměnitelného audit logu.
            </p>

            <div className="space-y-2">
              {hasLoginAccount && (
                <button
                  type="button"
                  onClick={() => setAuthMethod("password")}
                  className={cn(
                    "w-full text-left rounded-md border-2 p-3 transition-colors",
                    authMethod === "password"
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                      : "border-gray-200 dark:border-gray-700 hover:border-gray-300"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <KeyRound className="h-5 w-5 text-blue-600" />
                    <div>
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        Heslo do aplikace
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        Zadejte heslo, kterým se přihlašujete do DigitalOZO.
                      </div>
                    </div>
                  </div>
                </button>
              )}

              <button
                type="button"
                onClick={() => setAuthMethod("sms_otp")}
                className={cn(
                  "w-full text-left rounded-md border-2 p-3 transition-colors",
                  authMethod === "sms_otp"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                    : "border-gray-200 dark:border-gray-700 hover:border-gray-300"
                )}
              >
                <div className="flex items-center gap-3">
                  <Smartphone className="h-5 w-5 text-emerald-600" />
                  <div>
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      SMS kód
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Pošleme 6místný kód na vaše tel. číslo (platnost 5 min).
                    </div>
                  </div>
                </div>
              </button>
            </div>

            {!hasLoginAccount && (
              <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                Tento zaměstnanec nemá vlastní login do aplikace, proto je
                možný pouze podpis přes SMS kód.
              </div>
            )}

            {error && (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={onClose}>Zrušit</Button>
              <Button
                onClick={() => { setError(null); initiateMut.mutate(authMethod); }}
                disabled={initiateMut.isPending}
              >
                {initiateMut.isPending ? "Odesílám…" : "Pokračovat"}
              </Button>
            </div>
          </>
        )}

        {step === "code" && (
          <>
            <div className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-200">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{smsInfo?.message ?? "SMS byla odeslána."}</span>
              </div>
              <p className="mt-1 text-xs opacity-80">
                Zadejte 6místný kód, který přišel na telefon zaměstnance.
                V demo režimu je kód vždy <strong>111111</strong>.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="otp">SMS kód</Label>
              <Input
                id="otp"
                inputMode="numeric"
                maxLength={6}
                placeholder="111111"
                value={codeOrPassword}
                onChange={(e) => setCodeOrPassword(e.target.value.replace(/\D/g, ""))}
                className="text-center text-2xl font-mono tracking-widest"
                autoFocus
              />
            </div>

            {error && (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="flex justify-between gap-2 pt-2">
              <Button variant="outline" onClick={() => setStep("choose")}>
                Zpět
              </Button>
              <Button
                onClick={() => { setError(null); verifyMut.mutate(); }}
                disabled={verifyMut.isPending || codeOrPassword.length !== 6}
              >
                {verifyMut.isPending ? "Ověřuji…" : "Podepsat"}
              </Button>
            </div>
          </>
        )}

        {step === "password" && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="pwd">Heslo zaměstnance</Label>
              <Input
                id="pwd"
                type="password"
                placeholder="Heslo do DigitalOZO"
                value={codeOrPassword}
                onChange={(e) => setCodeOrPassword(e.target.value)}
                autoFocus
              />
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Stejné heslo, kterým se {employeeName} přihlašuje do aplikace.
              </p>
            </div>

            {error && (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="flex justify-between gap-2 pt-2">
              <Button variant="outline" onClick={() => setStep("choose")}>
                Zpět
              </Button>
              <Button
                onClick={() => { setError(null); verifyMut.mutate(); }}
                disabled={verifyMut.isPending || codeOrPassword.length === 0}
              >
                {verifyMut.isPending ? "Ověřuji…" : "Podepsat"}
              </Button>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
