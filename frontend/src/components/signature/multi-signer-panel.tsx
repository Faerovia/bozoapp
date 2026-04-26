"use client";

/**
 * Multi-signer panel — pro dokumenty s více povinnými signátory
 * (typicky pracovní úraz: postižený + svědci + vedoucí).
 *
 * Použití:
 *   <MultiSignerPanel
 *     open={open}
 *     onClose={() => setOpen(false)}
 *     docType="accident_report"
 *     docId={report.id}
 *     onCompleted={() => refetch()}
 *   />
 *
 * Workflow:
 * 1. Po otevření načte GET /{module}/{id}/signers
 * 2. Vykreslí seznam s avatary (✓ podepsáno / ☐ čeká).
 * 3. Klik na nepodepsaného signera otevře SignatureDialog.
 * 4. Po úspěšném podpisu refetchne list a aktualizuje stav.
 *
 * Pro accident_report se URL shrnuje na /accident-reports/{id}/signers.
 * Pokud chceš použít na jiném modulu (training_attempt), URL musí být
 * konfigurovatelná — nyní hardcoded pro accident_report.
 */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Smartphone, KeyRound, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { SignatureDocType } from "@/types/api";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { SignatureDialog } from "./signature-dialog";
import { cn } from "@/lib/utils";

interface SignerInfo {
  employee_id: string;
  full_name: string;
  role_label: string;
  has_login_account: boolean;
  has_phone: boolean;
  signed: boolean;
  signed_at: string | null;
  signature_id: string | null;
}

interface MultiSignerPanelProps {
  open: boolean;
  onClose: () => void;
  docType: SignatureDocType;
  docId: string;
  /** URL pro fetch signerů — default: /accident-reports/{id}/signers */
  signersUrl?: string;
  /** Po úspěšném dokončení (všichni podepsali) */
  onCompleted?: () => void;
  title?: string;
}

export function MultiSignerPanel({
  open,
  onClose,
  docType,
  docId,
  signersUrl,
  onCompleted,
  title = "Digitální podpisy účastníků",
}: MultiSignerPanelProps) {
  const qc = useQueryClient();
  const [signing, setSigning] = useState<SignerInfo | null>(null);
  const url = signersUrl ?? `/accident-reports/${docId}/signers`;

  const { data: signers = [], isLoading, refetch } = useQuery<SignerInfo[]>({
    queryKey: ["signers", docType, docId],
    queryFn: () => api.get(url),
    enabled: open,
  });

  const allSigned = signers.length > 0 && signers.every((s) => s.signed);
  const anyCantSign = signers.some(
    (s) => !s.signed && !s.has_login_account && !s.has_phone,
  );

  return (
    <Dialog open={open} onClose={onClose} title={title} size="md">
      <div className="space-y-4">
        {isLoading ? (
          <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
            Načítám…
          </div>
        ) : signers.length === 0 ? (
          <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 px-3 py-3 text-sm text-amber-800 dark:text-amber-200">
            Tento dokument nemá žádné požadované digitální signátory
            (může obsahovat externí účastníky → fyzický podpis).
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Pro každého interního účastníka klikni na řádek a nech ho
              podepsat. Po podepsání všech se status změní na &bdquo;Podepsáno&ldquo;.
            </p>

            {anyCantSign && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 px-3 py-2 text-xs text-red-800 dark:text-red-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                Některý účastník nemá login ani telefonní číslo —
                nemůže podepsat. Doplň mu telefon v evidenci nebo nech
                úraz fyzicky podepsat.
              </div>
            )}

            <ul className="divide-y divide-gray-100 dark:divide-gray-700 rounded-md border border-gray-200 dark:border-gray-700">
              {signers.map((s) => {
                const canSign = s.has_login_account || s.has_phone;
                return (
                  <li
                    key={s.employee_id}
                    className={cn(
                      "px-3 py-2.5 flex items-center justify-between gap-3",
                      s.signed && "bg-emerald-50/50 dark:bg-emerald-900/10",
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {s.signed ? (
                        <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                      ) : (
                        <Circle className="h-5 w-5 text-gray-300 dark:text-gray-600 shrink-0" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-gray-900 dark:text-gray-100 truncate">
                          {s.full_name}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2 mt-0.5">
                          <span>{s.role_label}</span>
                          {!s.signed && (
                            <>
                              {s.has_login_account && (
                                <span className="inline-flex items-center gap-0.5">
                                  <KeyRound className="h-3 w-3" /> heslo
                                </span>
                              )}
                              {s.has_phone && (
                                <span className="inline-flex items-center gap-0.5">
                                  <Smartphone className="h-3 w-3" /> SMS
                                </span>
                              )}
                            </>
                          )}
                          {s.signed && s.signed_at && (
                            <span className="text-emerald-700 dark:text-emerald-300">
                              {new Date(s.signed_at).toLocaleString("cs-CZ")}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {!s.signed && (
                      <Button
                        size="sm"
                        variant={canSign ? "default" : "outline"}
                        disabled={!canSign}
                        onClick={() => setSigning(s)}
                      >
                        Podepsat
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>

            {allSigned && (
              <div className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-300 dark:border-emerald-700 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-200">
                ✓ Všichni účastníci digitálně podepsali. Dokument je
                kompletně podepsán.
              </div>
            )}
          </>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="outline" onClick={onClose}>Zavřít</Button>
        </div>
      </div>

      {signing && (
        <SignatureDialog
          open={!!signing}
          onClose={() => setSigning(null)}
          docType={docType}
          docId={docId}
          employeeId={signing.employee_id}
          employeeName={signing.full_name}
          hasLoginAccount={signing.has_login_account}
          title={`${signing.role_label}: ${signing.full_name}`}
          onSigned={async () => {
            setSigning(null);
            await refetch();
            // Invaliduj parent listy, aby se aktualizovaly badges
            qc.invalidateQueries({ queryKey: ["accident-reports"] });
            // Pokud teď all signed, zavolej onCompleted
            const updated = await api.get<SignerInfo[]>(url);
            if (updated.length > 0 && updated.every((s) => s.signed)) {
              onCompleted?.();
            }
          }}
        />
      )}
    </Dialog>
  );
}
