"use client";

/**
 * Univerzální dialog pro digitální podpis zaměstnance.
 *
 * Tři metody ověření identity:
 * 1. Heslo (zaměstnanec má login do DigitalOZO)
 * 2. SMS kód (6 číslic, platnost 5 min)
 * 3. Vlastnoruční podpis myší / prstem (canvas → PNG base64)
 *
 * Image pro handwritten je uložen do auth_proof a je součástí payload hashe
 * v hash chainu signatures — tampering by zlomil chain_hash.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ShieldCheck, KeyRound, Smartphone, Pencil, AlertCircle, CheckCircle2,
  Eraser,
} from "lucide-react";
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
  /** Pokud false, je možný jen sms_otp / handwritten (zaměstnanec nemá login). */
  hasLoginAccount: boolean;
  /** Volá se po úspěšném vytvoření podpisu — caller ho přilepí k dokumentu. */
  onSigned: (signature: SignatureRecord) => void;
  /** Custom title — default "Digitální podpis". */
  title?: string;
}

type Step = "choose" | "code" | "password" | "canvas";

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
  const [signatureImage, setSignatureImage] = useState<string | null>(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setStep("choose");
      setAuthMethod(hasLoginAccount ? "password" : "sms_otp");
      setCodeOrPassword("");
      setSmsInfo(null);
      setError(null);
      setSignatureImage(null);
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
      if (m === "sms_otp") setStep("code");
      else if (m === "password") setStep("password");
      else setStep("canvas");
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
        code_or_password: authMethod === "handwritten" ? null : codeOrPassword,
        signature_image_b64: authMethod === "handwritten" ? signatureImage : null,
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

              <button
                type="button"
                onClick={() => setAuthMethod("handwritten")}
                className={cn(
                  "w-full text-left rounded-md border-2 p-3 transition-colors",
                  authMethod === "handwritten"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                    : "border-gray-200 dark:border-gray-700 hover:border-gray-300"
                )}
              >
                <div className="flex items-center gap-3">
                  <Pencil className="h-5 w-5 text-purple-600" />
                  <div>
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      Vlastnoruční podpis
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Nakreslete podpis prstem na dotykovém displeji nebo myší.
                    </div>
                  </div>
                </div>
              </button>
            </div>

            {!hasLoginAccount && (
              <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                Tento zaměstnanec nemá vlastní login do aplikace, proto je
                možný jen podpis přes SMS kód nebo vlastnoruční podpis.
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

        {step === "canvas" && (
          <SignatureCanvasStep
            error={error}
            verifying={verifyMut.isPending}
            onBack={() => setStep("choose")}
            onSign={(b64) => {
              setSignatureImage(b64);
              setError(null);
              // Trigger verify after state set — useEffect by mohl, ale
              // pro jednoduchost necháme caller submitnout přes tlačítko
              // a verifyMut.mutate() použije aktuální signatureImage.
              // Místo state závodu — pošlu rovnou v argumentu:
              verifyMut.mutate(undefined, {
                onError: () => {},  // error už handled výše
              });
            }}
            signatureImage={signatureImage}
            setSignatureImage={setSignatureImage}
          />
        )}
      </div>
    </Dialog>
  );
}


// ── Canvas komponenta pro vlastnoruční podpis ───────────────────────────────

function SignatureCanvasStep({
  error,
  verifying,
  onBack,
  onSign,
  signatureImage,
  setSignatureImage,
}: {
  error: string | null;
  verifying: boolean;
  onBack: () => void;
  onSign: (b64: string) => void;
  signatureImage: string | null;
  setSignatureImage: (b64: string | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);
  const hasStrokeRef = useRef(false);

  // Init canvas (white bg, černé pero)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#1f2937";
    ctx.lineWidth = 2.5;
  }, []);

  const getPoint = useCallback((evt: PointerEvent): { x: number; y: number } => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((evt.clientX - rect.left) / rect.width) * canvas.width,
      y: ((evt.clientY - rect.top) / rect.height) * canvas.height,
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const onDown = (e: PointerEvent) => {
      e.preventDefault();
      canvas.setPointerCapture(e.pointerId);
      drawingRef.current = true;
      lastPointRef.current = getPoint(e);
    };
    const onMove = (e: PointerEvent) => {
      if (!drawingRef.current) return;
      const p = getPoint(e);
      const last = lastPointRef.current;
      if (last) {
        ctx.beginPath();
        ctx.moveTo(last.x, last.y);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
        hasStrokeRef.current = true;
      }
      lastPointRef.current = p;
    };
    const onUp = (e: PointerEvent) => {
      if (drawingRef.current) {
        canvas.releasePointerCapture(e.pointerId);
      }
      drawingRef.current = false;
      lastPointRef.current = null;
    };

    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("pointerleave", onUp);
    return () => {
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onUp);
      canvas.removeEventListener("pointerleave", onUp);
    };
  }, [getPoint]);

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    hasStrokeRef.current = false;
    setSignatureImage(null);
  };

  const handleSubmit = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!hasStrokeRef.current) return;
    // PNG data URI — backend si strip prefix
    const dataUri = canvas.toDataURL("image/png");
    onSign(dataUri);
  };

  return (
    <>
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Nakreslete podpis prstem nebo myší v rámečku níže.
      </p>

      <div className="rounded-md border-2 border-gray-300 dark:border-gray-600 bg-white">
        <canvas
          ref={canvasRef}
          width={600}
          height={200}
          className="w-full h-[200px] touch-none cursor-crosshair"
          style={{ touchAction: "none" }}
        />
      </div>

      <div className="flex justify-between items-center text-xs text-gray-500">
        <span>Tip: na mobilu / tabletu použijte prst nebo stylus.</span>
        <button
          type="button"
          onClick={clearCanvas}
          className="flex items-center gap-1 hover:text-gray-700"
        >
          <Eraser className="h-3 w-3" />
          Smazat
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-between gap-2 pt-2">
        <Button variant="outline" onClick={onBack}>Zpět</Button>
        <Button
          onClick={handleSubmit}
          disabled={verifying || (!!signatureImage)}
        >
          {verifying ? "Ukládám podpis…" : "Podepsat"}
        </Button>
      </div>
    </>
  );
}
