"use client";

/**
 * Modal pro podpis školení.
 *
 * Flow:
 *  - simple (bez ZES): canvas → POST /sign
 *  - ZES: krok 1 — request OTP (channel: email|sms|auto), krok 2 — verify OTP,
 *    krok 3 — canvas → POST /sign s otp_id + method=qes
 *
 * Použití:
 *   <TrainingSignDialog
 *     assignmentId="..."
 *     requiresQes={training.requires_qes}
 *     open={open}
 *     onClose={() => ...}
 *     onSigned={() => refetch}
 *   />
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Mail, MessageSquare, AlertTriangle, CheckCircle2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SignaturePad } from "./signature-pad";

interface RequestOtpResponse {
  otp_id: string;
  sent_to: string;
  channel: "email" | "sms";
}

interface VerifyOtpResponse {
  otp_id: string;
  verified: boolean;
}

interface SignResponse {
  assignment_id: string;
  signed_at: string;
  method: string;
}

interface Props {
  assignmentId: string;
  requiresQes: boolean;
  open: boolean;
  onClose: () => void;
  onSigned?: () => void;
}

interface ContentProps {
  assignmentId: string;
  requiresQes: boolean;
  onCancel: () => void;
  onSigned?: () => void;
}

type Step = "intro" | "otp-sent" | "canvas" | "submitting" | "done";

/**
 * Inline content (bez Dialog wrapperu) — pro embedding do existujících
 * dialogů (např. TrainingRunFlow už je uvnitř Dialog).
 */
export function TrainingSignContent({
  assignmentId, requiresQes, onCancel, onSigned,
}: ContentProps) {
  const [step, setStep] = useState<Step>("intro");
  const [error, setError] = useState<string | null>(null);
  const [signature, setSignature] = useState<string | null>(null);

  // OTP state (jen pro ZES)
  const [otpId, setOtpId] = useState<string | null>(null);
  const [otpSentTo, setOtpSentTo] = useState<string | null>(null);
  const [otpChannel, setOtpChannel] = useState<"email" | "sms" | null>(null);
  const [code, setCode] = useState("");

  function reset() {
    setStep("intro");
    setError(null);
    setSignature(null);
    setOtpId(null);
    setOtpSentTo(null);
    setOtpChannel(null);
    setCode("");
  }

  function handleClose() {
    reset();
    onCancel();
  }

  // ── Mutations ─────────────────────────────────────────────────────────────

  const requestOtp = useMutation<
    RequestOtpResponse, ApiError, "email" | "sms" | undefined
  >({
    mutationFn: (channel) =>
      api.post<RequestOtpResponse>(
        `/trainings/assignments/${assignmentId}/request-otp`,
        channel ? { channel } : {},
      ),
    onSuccess: (data) => {
      setOtpId(data.otp_id);
      setOtpSentTo(data.sent_to);
      setOtpChannel(data.channel);
      setStep("otp-sent");
      setError(null);
    },
    onError: (err) => setError(err.detail || "OTP nebylo odesláno"),
  });

  const verifyOtp = useMutation<VerifyOtpResponse, ApiError, void>({
    mutationFn: () =>
      api.post<VerifyOtpResponse>(
        `/trainings/assignments/${assignmentId}/verify-otp`,
        { otp_id: otpId, code },
      ),
    onSuccess: (data) => {
      if (data.verified) {
        setStep("canvas");
        setError(null);
      } else {
        setError("OTP nebyl ověřen");
      }
    },
    onError: (err) => setError(err.detail || "Nesprávný kód"),
  });

  const sign = useMutation<SignResponse, ApiError, void>({
    mutationFn: () =>
      api.post<SignResponse>(
        `/trainings/assignments/${assignmentId}/sign`,
        {
          signature_image_b64: signature,
          method: requiresQes ? "qes" : "simple",
          otp_id: requiresQes ? otpId : undefined,
        },
      ),
    onSuccess: () => {
      setStep("done");
      onSigned?.();
    },
    onError: (err) => setError(err.detail || "Podpis se nepodařilo uložit"),
  });

  // ── Render ────────────────────────────────────────────────────────────────

  const _title = requiresQes
    ? "Podpis školení (ZES — kvalifikovaný)"
    : "Podpis školení";

  void _title;
  return (
    <div className="space-y-4">
      {/* INTRO */}
      {step === "intro" && (
        <div className="space-y-4">
          {requiresQes ? (
            <>
              <div className="rounded-md bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
                <AlertTriangle className="h-4 w-4 inline mr-2" />
                Toto školení vyžaduje <strong>kvalifikovaný elektronický podpis (ZES)</strong>.
                Než se podepíšete, pošleme vám 6místný kód na váš email nebo SMS.
              </div>
              <div className="space-y-2">
                <Label>Kam poslat kód?</Label>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => requestOtp.mutate("email")}
                    loading={requestOtp.isPending}
                  >
                    <Mail className="h-4 w-4 mr-2" /> Email
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => requestOtp.mutate("sms")}
                    loading={requestOtp.isPending}
                  >
                    <MessageSquare className="h-4 w-4 mr-2" /> SMS
                  </Button>
                </div>
                <p className="text-xs text-gray-500">
                  Pokud nemáte jednu z možností, zvolte tu druhou.
                </p>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-gray-700">
                Podepište školení vlastním podpisem prstem nebo myší. Server
                uloží podpis spolu s časovým razítkem a vaším přihlášením
                jako důkaz absolvování.
              </p>
              <Button onClick={() => setStep("canvas")} size="lg">
                Pokračovat na podpis
              </Button>
            </>
          )}
          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 inline mr-2" />
              {error}
            </div>
          )}
        </div>
      )}

      {/* OTP SENT — verify */}
      {step === "otp-sent" && (
        <div className="space-y-4">
          <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-800">
            Kód byl odeslán {otpChannel === "sms" ? "SMS" : "emailem"} na{" "}
            <strong>{otpSentTo}</strong>. Platí 10 minut.
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="otp-code">6místný kód</Label>
            <Input
              id="otp-code"
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="123456"
              className="text-center text-lg tracking-widest"
            />
          </div>
          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 inline mr-2" />
              {error}
            </div>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setStep("intro")}
            >
              Zpět
            </Button>
            <Button
              className="flex-1"
              disabled={code.length !== 6 || verifyOtp.isPending}
              loading={verifyOtp.isPending}
              onClick={() => verifyOtp.mutate()}
            >
              Ověřit kód
            </Button>
          </div>
        </div>
      )}

      {/* CANVAS — sign */}
      {step === "canvas" && (
        <div className="space-y-4">
          <p className="text-sm text-gray-700">
            Podepište se v rámečku níže. Server uloží podpis a označí
            školení za platné.
          </p>
          <SignaturePad
            onChange={setSignature}
            height={200}
          />
          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 inline mr-2" />
              {error}
            </div>
          )}
          <Button
            onClick={() => sign.mutate()}
            disabled={!signature || sign.isPending}
            loading={sign.isPending}
            className="w-full"
            size="lg"
          >
            Odeslat podpis
          </Button>
        </div>
      )}

      {/* DONE */}
      {step === "done" && (
        <div className="space-y-4 text-center py-4">
          <CheckCircle2 className="h-16 w-16 text-green-600 mx-auto" />
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              Školení podepsáno
            </h3>
            <p className="text-sm text-gray-600 mt-1">
              Podpis byl uložen. Nyní se zobrazíš na prezenční listině.
            </p>
          </div>
          <Button onClick={handleClose} className="w-full">
            Zavřít
          </Button>
        </div>
      )}
    </div>
  );
}


/**
 * Standalone Dialog wrapper — pro samostatné použití (admin shared tablet).
 * Pro embedding do existujícího dialogu použij <TrainingSignContent>.
 */
export function TrainingSignDialog({
  assignmentId, requiresQes, open, onClose, onSigned,
}: Props) {
  const title = requiresQes
    ? "Podpis školení (ZES — kvalifikovaný)"
    : "Podpis školení";
  return (
    <Dialog open={open} onClose={onClose} title={title} size="md">
      <TrainingSignContent
        assignmentId={assignmentId}
        requiresQes={requiresQes}
        onCancel={onClose}
        onSigned={onSigned}
      />
    </Dialog>
  );
}
