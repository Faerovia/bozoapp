"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Plus,
  Pencil,
  Trash2,
  Users,
  FileUp,
  FileText,
  ClipboardList,
  Download,
  PlayCircle,
  CheckCircle2,
  XCircle,
  GraduationCap,
  ChevronLeft,
  ChevronRight,
  Award,
  Upload,
  Eye,
  HelpCircle,
} from "lucide-react";
import { TestQuestionsDialog } from "@/components/test-questions-dialog";
import { SignatureDialog } from "@/components/signature/signature-dialog";
import { api, ApiError, uploadFile } from "@/lib/api";
import type {
  AssignmentCreateResponse,
  Employee,
  JobPosition,
  Plant,
  StartTestResponse,
  SubmitTestResponse,
  TrainerKind,
  Training,
  TrainingAssignment,
  TrainingType,
  UserResponse,
  Workplace,
} from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { TrainingSignContent } from "@/components/training-sign-dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const TRAINING_TYPE_LABEL: Record<TrainingType, string> = {
  bozp: "BOZP",
  po: "Požární ochrana",
  other: "Ostatní",
};

const TRAINER_KIND_LABEL: Record<TrainerKind, string> = {
  ozo_bozp: "OZO BOZP",
  ozo_po: "OZO PO",
  employer: "Zaměstnavatel",
};

const VALIDITY_COLORS: Record<string, string> = {
  pending: "bg-blue-100 text-blue-700",
  overdue: "bg-red-100 text-red-700",
  valid: "bg-green-100 text-green-700",
  expiring_soon: "bg-amber-100 text-amber-700",
  expired: "bg-red-100 text-red-700",
  no_expiry: "bg-gray-100 text-gray-500",
};

const VALIDITY_LABEL: Record<string, string> = {
  pending: "Čeká na splnění",
  overdue: "Po termínu",
  valid: "Platné",
  expiring_soon: "Brzy expiruje",
  expired: "Expirované",
  no_expiry: "Bez expirace",
};

const SELECT_CLS =
  "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const ADMIN_ROLES = ["admin", "ozo", "hr_manager"];

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("cs-CZ");
}

function formatDateTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString("cs-CZ")} ${d.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" })}`;
}

// ── Router podle role + URL parametru ───────────────────────────────────────
//
// Sidebar má 2 položky:
//   - "Školení"          → /trainings           (admin pohled — správa šablon)
//   - "Školící centrum"  → /trainings?view=my   (employee pohled — moje přiřazená)
//
// Logika:
//   - non-admin role (employee/lead_worker/equipment_responsible) → vždy EmployeeView
//   - admin role (OZO/HR) → AdminView (default) NEBO EmployeeView (?view=my)

function TrainingsPageInner() {
  const { data: me, isLoading } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });
  const searchParams = useSearchParams();
  const view = searchParams.get("view");

  if (isLoading || !me)
    return <div className="p-6 text-sm text-gray-400">Načítám…</div>;

  if (!ADMIN_ROLES.includes(me.role)) return <EmployeeView />;
  return view === "my" ? <EmployeeView /> : <AdminView />;
}

export default function TrainingsPage() {
  // useSearchParams() musí být uvnitř <Suspense> (Next.js 15 prerender rule).
  return (
    <Suspense fallback={<div className="p-6 text-sm text-gray-400">Načítám…</div>}>
      <TrainingsPageInner />
    </Suspense>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Admin view — OZO/HR spravuje šablony + přiřazuje zaměstnancům
// ════════════════════════════════════════════════════════════════════════════

const trainingSchema = z.object({
  title: z.string().min(1, "Název je povinný"),
  training_type: z.enum(["bozp", "po", "other"]),
  trainer_kind: z.enum(["ozo_bozp", "ozo_po", "employer"]),
  valid_months: z.coerce.number().int().positive().max(600),
  notes: z.string().optional(),
  outline_text: z.string().optional(),
  duration_hours: z.coerce.number().min(0).max(999).optional().or(z.literal("")),
  // Unifikovaný flag (#105): zaškrtnuto = plný signature flow (autor +
  // OZO schválení + zaměstnanec ověřený podpis). Backend si dopočítá
  // `requires_ozo_approval` z role autora. Klient ho už neposílá samostatně.
  requires_qes: z.boolean().optional(),
  knowledge_test_required: z.boolean().optional(),
});

type TrainingFormData = z.infer<typeof trainingSchema>;

function AdminView() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editTraining, setEditTraining] = useState<Training | null>(null);
  const [assignTraining, setAssignTraining] = useState<Training | null>(null);
  const [testTraining, setTestTraining] = useState<Training | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  // Signing flow pro autora / OZO obsahu školení (#105). Po podpisu
  // přes SignatureDialog (docType='training_content') musíme zavolat
  // attach-author-signature nebo approve endpoint.
  const [signContent, setSignContent] = useState<{
    training: Training;
    mode: "author" | "approve";
  } | null>(null);

  const { data: me } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });
  const authorIsOzo = me?.role === "ozo";

  const { data: trainings = [], isLoading } = useQuery<Training[]>({
    queryKey: ["trainings"],
    queryFn: () => api.get("/trainings"),
  });

  const createMutation = useMutation({
    mutationFn: (data: TrainingFormData) => api.post<Training>("/trainings", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trainings"] });
      setCreateOpen(false);
      setServerError(null);
    },
    onError: (err) =>
      setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TrainingFormData> }) =>
      api.patch<Training>(`/trainings/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trainings"] });
      setServerError(null);
    },
    onError: (err) =>
      setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/trainings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trainings"] }),
  });

  return (
    <div>
      <Header
        title="Školení"
        actions={
          <Button
            onClick={() => {
              setServerError(null);
              setCreateOpen(true);
            }}
            size="sm"
          >
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat školení
          </Button>
        }
      />

      <div className="p-6">
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-8 text-sm text-gray-400">Načítám…</div>
            ) : trainings.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <GraduationCap className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádná školení</p>
                <p className="text-xs mt-1">Vytvořte první šablonu tlačítkem výše</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Název</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Typ</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Školitel</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Platnost</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Obsah</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Test</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                    <th className="py-3 px-4" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {trainings.map((t) => (
                    <tr key={t.id} className="hover:bg-gray-50">
                      <td className="py-3 px-4 font-medium text-gray-900">{t.title}</td>
                      <td className="py-3 px-4 text-gray-600">
                        {TRAINING_TYPE_LABEL[t.training_type]}
                      </td>
                      <td className="py-3 px-4 text-gray-600">
                        {TRAINER_KIND_LABEL[t.trainer_kind]}
                      </td>
                      <td className="py-3 px-4 text-gray-600">{t.valid_months} měsíců</td>
                      <td className="py-3 px-4 text-gray-600">
                        {t.content_pdf_path ? (
                          <span className="text-green-600 text-xs">
                            <FileText className="h-3.5 w-3.5 inline" /> PDF
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-gray-600">
                        {t.has_test ? (
                          <span className="text-green-600 text-xs">
                            {t.question_count} otázek ({t.pass_percentage}%)
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {t.status === "pending_approval" ? (
                          <span
                            className="rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-2 py-0.5 text-xs font-medium"
                            title="Čeká na schválení OZO"
                          >
                            ⏳ Schválení
                          </span>
                        ) : t.status === "archived" ? (
                          <span className="rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 px-2 py-0.5 text-xs font-medium">
                            Archiv
                          </span>
                        ) : t.requires_qes && !t.author_signature_id ? (
                          <span
                            className="rounded-full bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 px-2 py-0.5 text-xs font-medium"
                            title="Aktivní, ale autor obsahu nepodepsal"
                          >
                            ⚠ Bez podpisu
                          </span>
                        ) : (
                          <span className="rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 text-xs font-medium">
                            ✓ Aktivní
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center justify-end gap-1">
                          {t.requires_qes && t.status === "pending_approval" && authorIsOzo && (
                            <button
                              onClick={() => setSignContent({ training: t, mode: "approve" })}
                              className="rounded-md border border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 px-2 py-1 text-xs font-medium"
                              title="Schválit školení (OZO podepíše obsah)"
                            >
                              Schválit
                            </button>
                          )}
                          {t.requires_qes && t.status === "active" && !t.author_signature_id && (
                            <button
                              onClick={() => setSignContent({ training: t, mode: "author" })}
                              className="rounded-md border border-blue-300 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 hover:bg-blue-100 px-2 py-1 text-xs font-medium"
                              title="Podepsat obsah školení (autor)"
                            >
                              Podepsat
                            </button>
                          )}
                          <button
                            onClick={() => {
                              if (t.status !== "active") {
                                alert(
                                  t.status === "pending_approval"
                                    ? "Školení čeká na schválení OZO — nelze přiřadit zaměstnancům."
                                    : "Školení je archivované.",
                                );
                                return;
                              }
                              setServerError(null);
                              setAssignTraining(t);
                            }}
                            disabled={t.status !== "active"}
                            className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 disabled:opacity-30 disabled:hover:bg-transparent disabled:cursor-not-allowed"
                            title={t.status === "active" ? "Přidělit zaměstnance" : "Nelze přiřadit (čeká na schválení / archiv)"}
                          >
                            <Users className="h-4 w-4" />
                          </button>
                          <button
                            onClick={async () => {
                              const resp = await fetch(
                                `/api/v1/trainings/${t.id}/attendance-list.pdf`,
                              );
                              if (!resp.ok) {
                                alert("Stažení prezenční listiny selhalo");
                                return;
                              }
                              const blob = await resp.blob();
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a");
                              a.href = url;
                              a.download = `prezencni-listina-${t.title.replace(/\W/g, "_")}.pdf`;
                              a.click();
                              URL.revokeObjectURL(url);
                            }}
                            className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                            title="Stáhnout prezenční listinu"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => setTestTraining(t)}
                            className="rounded p-1 text-gray-400 hover:text-purple-600 hover:bg-purple-50"
                            title="Editor otázek testu"
                          >
                            <HelpCircle className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              setServerError(null);
                              setEditTraining(t);
                            }}
                            className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                            title="Upravit"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              if (
                                confirm(
                                  `Smazat školení "${t.title}"? Tím se smažou i všechna přiřazení.`
                                )
                              )
                                deleteMutation.mutate(t.id);
                            }}
                            className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                            title="Smazat"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nové školení"
        size="lg"
      >
        <TrainingForm
          onSubmit={(d) => createMutation.mutate(d)}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
        />
      </Dialog>

      <Dialog
        open={!!editTraining}
        onClose={() => setEditTraining(null)}
        title={editTraining ? `Upravit: ${editTraining.title}` : ""}
        size="lg"
      >
        {editTraining && (
          <EditTrainingBody
            training={editTraining}
            onSubmit={(d) => updateMutation.mutate({ id: editTraining.id, data: d })}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
          />
        )}
      </Dialog>

      <Dialog
        open={!!assignTraining}
        onClose={() => setAssignTraining(null)}
        title={assignTraining ? `Přidělit zaměstnance — ${assignTraining.title}` : ""}
        size="lg"
      >
        {assignTraining && (
          <AssignEmployeesBody
            training={assignTraining}
            onDone={() => setAssignTraining(null)}
          />
        )}
      </Dialog>

      <TestQuestionsDialog
        open={!!testTraining}
        onClose={() => setTestTraining(null)}
        trainingId={testTraining?.id ?? null}
        trainingTitle={testTraining?.title ?? ""}
      />

      {signContent && (
        <TrainingContentSigner
          training={signContent.training}
          mode={signContent.mode}
          onClose={() => setSignContent(null)}
          onDone={() => {
            setSignContent(null);
            qc.invalidateQueries({ queryKey: ["trainings"] });
          }}
        />
      )}
    </div>
  );
}

// ── Signing wrapper pro autor / OZO podpis obsahu školení (#105) ────────────
//
// Načte employee_id current usera z /auth/me/employee, otevře SignatureDialog
// s docType='training_content' a po úspěšném podpisu zavolá:
// - mode='author' → POST /trainings/{id}/attach-author-signature
// - mode='approve' → POST /trainings/{id}/approve

function TrainingContentSigner({
  training,
  mode,
  onClose,
  onDone,
}: {
  training: Training;
  mode: "author" | "approve";
  onClose: () => void;
  onDone: () => void;
}) {
  const { data: meEmp, isLoading } = useQuery<{
    employee_id: string | null;
    full_name: string;
    has_login_account: boolean;
    has_phone: boolean;
  }>({
    queryKey: ["me-employee"],
    queryFn: () => api.get("/auth/me/employee"),
  });

  if (isLoading || !meEmp) return null;

  if (!meEmp.employee_id) {
    // User nemá employee record — nelze digitálně podepsat
    return (
      <Dialog open onClose={onClose} title="Podpis nelze provést" size="md">
        <div className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Tvůj uživatelský účet nemá napojený záznam zaměstnance v evidenci,
            proto nelze digitálně podepsat. Doplň si svůj záznam v
            modulu Zaměstnanci nebo požádej OZO o pomoc.
          </p>
          <div className="flex justify-end">
            <Button variant="outline" onClick={onClose}>Zavřít</Button>
          </div>
        </div>
      </Dialog>
    );
  }

  return (
    <SignatureDialog
      open
      onClose={onClose}
      docType="training_content"
      docId={training.id}
      employeeId={meEmp.employee_id}
      employeeName={meEmp.full_name}
      hasLoginAccount={meEmp.has_login_account}
      title={
        mode === "approve"
          ? `Schválení OZO: ${training.title}`
          : `Podpis autora obsahu: ${training.title}`
      }
      onSigned={async (sig) => {
        try {
          if (mode === "approve") {
            await api.post(`/trainings/${training.id}/approve`, {
              signature_id: sig.id,
            });
          } else {
            await api.post(`/trainings/${training.id}/attach-author-signature`, {
              signature_id: sig.id,
            });
          }
          onDone();
        } catch (err) {
          alert(
            err instanceof ApiError ? err.detail : "Připojení podpisu selhalo",
          );
        }
      }}
    />
  );
}

// ── Volba metody podpisu pro zaměstnance po dokončení školení (#105) ─────
//
// Po dokončení školení (mark-read nebo úspěšný test) má zaměstnanec dvě
// volby:
// 1) Canvas + email/SMS OTP (stávající legacy flow přes TrainingSignContent)
// 2) Univerzální digitální podpis přes heslo/SMS (nový, s hash chain
//    + RFC 3161 TSA kotvou)
//
// Pokud zaměstnanec zvolí univerzální cestu, otevře se SignatureDialog
// s docType='training_attempt', doc_id=assignment.id. Po úspěchu volá
// POST /trainings/assignments/{id}/attach-signature pro napojení na
// universal_signature_id sloupec assignment.

function TrainingSignChoice({
  assignment,
  onCancel,
  onSigned,
}: {
  assignment: TrainingAssignment;
  onCancel: () => void;
  onSigned: () => void;
}) {
  const [method, setMethod] = useState<"canvas" | "universal" | null>(null);

  if (method === "canvas") {
    return (
      <TrainingSignContent
        assignmentId={assignment.id}
        requiresQes={!!assignment.training_requires_qes}
        onCancel={() => setMethod(null)}
        onSigned={onSigned}
      />
    );
  }

  if (method === "universal") {
    return (
      <UniversalAttemptSigner
        assignment={assignment}
        onClose={() => setMethod(null)}
        onSigned={onSigned}
      />
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Vyber způsob, jakým chceš podepsat absolvování školení.
      </p>

      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setMethod("canvas")}
          className="w-full text-left rounded-md border-2 border-gray-200 dark:border-gray-700 p-3 hover:border-blue-400 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Pencil className="h-5 w-5 text-blue-600" />
            <div>
              <div className="font-medium text-gray-900 dark:text-gray-100">
                Vlastnoruční podpis (canvas)
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                Nakreslíš podpis prstem nebo myší, volitelně OTP přes email/SMS.
              </div>
            </div>
          </div>
        </button>

        <button
          type="button"
          onClick={() => setMethod("universal")}
          className="w-full text-left rounded-md border-2 border-gray-200 dark:border-gray-700 p-3 hover:border-emerald-400 transition-colors"
        >
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <div>
              <div className="font-medium text-gray-900 dark:text-gray-100">
                Heslo nebo SMS kód
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                Ověř identitu heslem do aplikace nebo 6místným SMS kódem.
                Tamper-evident podpis (hash chain).
              </div>
            </div>
          </div>
        </button>
      </div>

      <div className="flex justify-end pt-2 border-t border-gray-100 dark:border-gray-700">
        <Button variant="outline" onClick={onCancel}>Zpět</Button>
      </div>
    </div>
  );
}

function UniversalAttemptSigner({
  assignment,
  onClose,
  onSigned,
}: {
  assignment: TrainingAssignment;
  onClose: () => void;
  onSigned: () => void;
}) {
  const { data: meEmp, isLoading } = useQuery<{
    employee_id: string | null;
    full_name: string;
    has_login_account: boolean;
    has_phone: boolean;
  }>({
    queryKey: ["me-employee"],
    queryFn: () => api.get("/auth/me/employee"),
  });

  if (isLoading || !meEmp) {
    return <div className="py-8 text-center text-sm text-gray-400">Načítám…</div>;
  }

  if (!meEmp.employee_id) {
    return (
      <div className="space-y-3">
        <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 px-3 py-3 text-sm text-amber-800 dark:text-amber-200">
          Tvůj uživatelský účet nemá napojený záznam zaměstnance. Pro
          digitální podpis přes heslo/SMS musí být účet napojen — kontaktuj
          OZO. Mezitím použij vlastnoruční podpis.
        </div>
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Zpět</Button>
        </div>
      </div>
    );
  }

  return (
    <SignatureDialog
      open
      onClose={onClose}
      docType="training_attempt"
      docId={assignment.id}
      employeeId={meEmp.employee_id}
      employeeName={meEmp.full_name}
      hasLoginAccount={meEmp.has_login_account}
      title={`Podpis školení: ${assignment.training_title ?? ""}`}
      onSigned={async (sig) => {
        try {
          await api.post(`/trainings/assignments/${assignment.id}/attach-signature`, {
            signature_id: sig.id,
          });
          onSigned();
        } catch (err) {
          alert(err instanceof ApiError ? err.detail : "Připojení podpisu selhalo");
        }
      }}
    />
  );
}

// ── Formulář pro šablonu ─────────────────────────────────────────────────────

function TrainingForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
}: {
  defaultValues?: Partial<TrainingFormData>;
  onSubmit: (d: TrainingFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<TrainingFormData>({
    resolver: zodResolver(trainingSchema),
    defaultValues: defaultValues ?? {
      training_type: "bozp",
      trainer_kind: "employer",
      valid_months: 12,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="title">Název školení *</Label>
        <Input id="title" {...register("title")} placeholder="např. BOZP vstupní školení" />
        {errors.title && <p className="text-xs text-red-600">{errors.title.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="training_type">Typ *</Label>
          <select id="training_type" {...register("training_type")} className={SELECT_CLS}>
            <option value="bozp">BOZP</option>
            <option value="po">Požární ochrana</option>
            <option value="other">Ostatní</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="trainer_kind">Školitel *</Label>
          <select id="trainer_kind" {...register("trainer_kind")} className={SELECT_CLS}>
            <option value="ozo_bozp">OZO BOZP</option>
            <option value="ozo_po">OZO PO</option>
            <option value="employer">Zaměstnavatel</option>
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="valid_months">Platnost (měsíce) *</Label>
        <Input id="valid_months" type="number" min="1" max="600" {...register("valid_months")} />
        <p className="text-xs text-gray-400">
          Platnost se počítá individuálně od data splnění každého zaměstnance.
        </p>
        {errors.valid_months && (
          <p className="text-xs text-red-600">{errors.valid_months.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="duration_hours">Délka školení (hodin)</Label>
          <Input
            id="duration_hours"
            type="number"
            step="0.5"
            min="0"
            max="999"
            {...register("duration_hours")}
            placeholder="např. 2"
          />
          <p className="text-xs text-gray-400">
            Zobrazí se na prezenční listině.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label className="flex items-center gap-2 cursor-pointer pt-7">
            <input
              type="checkbox"
              {...register("knowledge_test_required")}
              className="rounded border-gray-300"
            />
            <span className="text-sm">Znalosti ověřeny testem</span>
          </Label>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="outline_text">Osnova / náplň školení</Label>
        <textarea
          id="outline_text"
          {...register("outline_text")}
          rows={4}
          placeholder="Přehled bodů probíraných ve školení (zobrazí se v hlavičce prezenční listiny)"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {/* Sjednocený flag #105: zaškrtnuto = plný flow ověřených podpisů
          (autor + OZO schválení + zaměstnanec při dokončení testu, vše s
          hash chainem). Nezaškrtnuto = jen prezenční listina, žádné podpisy.
          Backend (create_training endpoint) automaticky doplní
          requires_ozo_approval podle role autora. */}
      <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-3 py-2">
        <Label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            {...register("requires_qes")}
            className="rounded border-gray-300"
          />
          <span className="text-sm font-medium text-amber-900 dark:text-amber-100">
            Je vyžadováno ověření podpisu školitele a školených zaměstnanců
          </span>
        </Label>
        <p className="text-xs text-amber-700 dark:text-amber-200 mt-1 ml-6">
          Při zaškrtnutí: školení musí podepsat autor obsahu, schválit OZO
          (pokud autor není OZO) a zaměstnanci se po dokončení testu ověří
          (heslem nebo SMS kódem). Vše se zapisuje do nezměnitelného audit logu
          s hash chainem. <br />
          Bez zaškrtnutí: žádné ověření, neeviduje se historie ani hash —
          stačí pouze prezenční listina.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Interní poznámky</Label>
        <textarea
          id="notes"
          {...register("notes")}
          rows={2}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {serverError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {serverError}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" loading={isSubmitting}>
          Uložit
        </Button>
      </div>
    </form>
  );
}

// ── Edit šablony + PDF + Test sekce ──────────────────────────────────────────

function EditTrainingBody({
  training,
  onSubmit,
  isSubmitting,
  serverError,
}: {
  training: Training;
  onSubmit: (d: TrainingFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["trainings"] });

  const pdfMutation = useMutation({
    mutationFn: (file: File) =>
      uploadFile(`/trainings/${training.id}/content`, file),
    onSuccess: refresh,
    onError: (err) =>
      alert(err instanceof ApiError ? err.detail : "Upload selhal"),
  });

  const testUploadMutation = useMutation({
    mutationFn: async ({ file, pass }: { file: File; pass: number }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("pass_percentage", pass.toString());
      const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : null;
      const res = await fetch(`/api/v1/trainings/${training.id}/test`, {
        method: "POST",
        headers: csrf ? { "X-CSRF-Token": csrf } : {},
        body: fd,
        credentials: "same-origin",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(res.status, err.detail ?? `HTTP ${res.status}`);
      }
      return res.json();
    },
    onSuccess: refresh,
    onError: (err) =>
      alert(err instanceof ApiError ? err.detail : "Upload testu selhal"),
  });

  const testDeleteMutation = useMutation({
    mutationFn: () => api.delete(`/trainings/${training.id}/test`),
    onSuccess: refresh,
  });

  return (
    <div className="space-y-6">
      <TrainingForm
        defaultValues={{
          title: training.title,
          training_type: training.training_type,
          trainer_kind: training.trainer_kind,
          valid_months: training.valid_months,
          notes: training.notes ?? "",
          requires_qes: training.requires_qes,
        }}
        onSubmit={onSubmit}
        isSubmitting={isSubmitting}
        serverError={serverError}
      />

      <div className="border-t border-gray-100 pt-4">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
          Obsah školení (PDF)
        </p>
        <div className="flex items-center gap-2">
          {training.content_pdf_path ? (
            <a
              href={`/api/v1/trainings/${training.id}/content`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-md bg-green-50 border border-green-200 px-3 py-1.5 text-xs text-green-800 hover:bg-green-100"
            >
              <FileText className="h-3.5 w-3.5" />
              Zobrazit nahraný PDF
            </a>
          ) : (
            <span className="text-xs text-gray-500">PDF není nahrán (volitelné)</span>
          )}
        </div>
        <div className="mt-2">
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) pdfMutation.mutate(f);
              e.target.value = "";
            }}
            className="block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
          />
          <p className="text-xs text-gray-400 mt-1">PDF max 3 MB. Nahráním přepíšeš stávající.</p>
        </div>
      </div>

      <div className="border-t border-gray-100 pt-4">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
          Test ke školení
        </p>
        {training.has_test ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm">
              <ClipboardList className="h-4 w-4 text-green-600" />
              <span>
                Nahrán test: <strong>{training.question_count} otázek</strong>, pro splnění nutno
                <strong> {training.pass_percentage}%</strong>
              </span>
            </div>
            <button
              onClick={() => {
                if (confirm("Smazat test? Existující pokusy zůstanou v evidenci."))
                  testDeleteMutation.mutate();
              }}
              className="text-xs text-red-600 hover:underline"
            >
              Odstranit test
            </button>
          </div>
        ) : (
          <TestUploadSection
            onUpload={(file, pass) => testUploadMutation.mutate({ file, pass })}
            loading={testUploadMutation.isPending}
          />
        )}
      </div>
    </div>
  );
}

function TestUploadSection({
  onUpload,
  loading,
}: {
  onUpload: (file: File, pass: number) => void;
  loading: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [pass, setPass] = useState<number>(80);

  return (
    <div className="space-y-3">
      <div className="rounded-md bg-blue-50 border border-blue-200 p-3 flex items-start gap-3">
        <FileText className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
        <div className="flex-1 text-xs text-blue-800">
          <p className="font-medium">Formát CSV</p>
          <p>
            První sloupec = otázka, sloupce 2–5 = 4 odpovědi (sloupec 2 je vždy správná).
            Min 5, max 25 otázek.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => window.open("/api/v1/trainings/test-template", "_blank")}
        >
          <Download className="h-3.5 w-3.5 mr-1" />
          Vzor
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2 space-y-1.5">
          <Label>CSV soubor s otázkami</Label>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pass_pct">Min % pro splnění</Label>
          <Input
            id="pass_pct"
            type="number"
            min="0"
            max="100"
            value={pass}
            onChange={(e) => setPass(Number(e.target.value))}
          />
        </div>
      </div>

      <Button
        onClick={() => file && onUpload(file, pass)}
        disabled={!file}
        loading={loading}
        size="sm"
      >
        <Upload className="h-4 w-4 mr-1.5" />
        Nahrát test
      </Button>
    </div>
  );
}

// ── Přidělit zaměstnance (multi-select s filtry) ─────────────────────────────

function AssignEmployeesBody({
  training,
  onDone,
}: {
  training: Training;
  onDone: () => void;
}) {
  const [nameFilter, setNameFilter] = useState("");
  const [plantFilter, setPlantFilter] = useState("");
  const [workplaceFilter, setWorkplaceFilter] = useState("");
  const [positionFilter, setPositionFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<AssignmentCreateResponse | null>(null);

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees", "active-for-assign"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 60 * 1000,
  });
  const { data: plants = [] } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants"),
    staleTime: 5 * 60 * 1000,
  });
  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces"],
    queryFn: () => api.get("/workplaces"),
    staleTime: 5 * 60 * 1000,
  });
  const { data: positions = [] } = useQuery<JobPosition[]>({
    queryKey: ["job-positions"],
    queryFn: () => api.get("/job-positions"),
    staleTime: 5 * 60 * 1000,
  });

  const workplacesForPlant = plantFilter
    ? workplaces.filter((w) => w.plant_id === plantFilter)
    : workplaces;

  const filtered = useMemo(() => {
    const q = nameFilter.trim().toLowerCase();
    return employees.filter((e) => {
      if (q) {
        const full = `${e.first_name} ${e.last_name}`.toLowerCase();
        if (!full.includes(q)) return false;
      }
      if (plantFilter && e.plant_id !== plantFilter) return false;
      if (workplaceFilter && e.workplace_id !== workplaceFilter) return false;
      if (positionFilter && e.job_position_id !== positionFilter) return false;
      return true;
    });
  }, [employees, nameFilter, plantFilter, workplaceFilter, positionFilter]);

  const visibleIds = filtered.map((e) => e.id);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));

  function toggleAllVisible() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const assignMutation = useMutation({
    mutationFn: (employeeIds: string[]) =>
      api.post<AssignmentCreateResponse>("/trainings/assignments", {
        training_id: training.id,
        employee_ids: employeeIds,
      }),
    onSuccess: (res) => setResult(res),
    onError: (err) =>
      alert(err instanceof ApiError ? err.detail : "Přiřazení selhalo"),
  });

  if (result) {
    return (
      <div className="space-y-4">
        <div className="rounded-md bg-green-50 border border-green-200 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-green-600 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-green-900">Přiřazení proběhlo</p>
              <p className="text-green-800 mt-0.5">
                Nově přiřazeno: <strong>{result.created_count}</strong>
                {result.skipped_existing_count > 0 && (
                  <>
                    {" · "}Přeskočeno (už přiřazeno):{" "}
                    <strong>{result.skipped_existing_count}</strong>
                  </>
                )}
              </p>
            </div>
          </div>
        </div>
        {result.errors.length > 0 && (
          <div className="rounded-md bg-red-50 border border-red-200 p-3 text-xs text-red-700 max-h-40 overflow-y-auto">
            <p className="font-medium mb-1">Chyby:</p>
            <ul className="list-disc list-inside space-y-0.5">
              {result.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex justify-end">
          <Button onClick={onDone}>Zavřít</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>
          <Label className="text-xs">Jméno</Label>
          <Input placeholder="Hledat…" value={nameFilter} onChange={(e) => setNameFilter(e.target.value)} />
        </div>
        <div>
          <Label className="text-xs">Provozovna</Label>
          <select
            value={plantFilter}
            onChange={(e) => {
              setPlantFilter(e.target.value);
              setWorkplaceFilter("");
            }}
            className={SELECT_CLS}
          >
            <option value="">Všechny</option>
            {plants.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label className="text-xs">Pracoviště</Label>
          <select
            value={workplaceFilter}
            onChange={(e) => setWorkplaceFilter(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">Všechna</option>
            {workplacesForPlant.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label className="text-xs">Pozice</Label>
          <select
            value={positionFilter}
            onChange={(e) => setPositionFilter(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">Všechny</option>
            {positions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="border border-gray-200 rounded-md overflow-hidden">
        <div className="max-h-80 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="py-2 px-3 w-10 text-center">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleAllVisible}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                </th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Jméno</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Os. č.</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Pozice</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Pracoviště</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-gray-400 text-sm">
                    Žádní zaměstnanci pro tento filtr
                  </td>
                </tr>
              ) : (
                filtered.map((e) => {
                  const pos = positions.find((p) => p.id === e.job_position_id);
                  const wp = workplaces.find((w) => w.id === e.workplace_id);
                  return (
                    <tr
                      key={e.id}
                      onClick={() => toggleOne(e.id)}
                      className={cn(
                        "hover:bg-gray-50 cursor-pointer",
                        selected.has(e.id) && "bg-blue-50"
                      )}
                    >
                      <td className="py-2 px-3 text-center">
                        <input
                          type="checkbox"
                          checked={selected.has(e.id)}
                          onChange={() => toggleOne(e.id)}
                          onClick={(ev) => ev.stopPropagation()}
                          className="h-4 w-4 rounded border-gray-300"
                        />
                      </td>
                      <td className="py-2 px-3">
                        {e.last_name} {e.first_name}
                      </td>
                      <td className="py-2 px-3 text-xs text-gray-500">
                        {e.personal_number || "—"}
                      </td>
                      <td className="py-2 px-3 text-xs text-gray-600">{pos?.name ?? "—"}</td>
                      <td className="py-2 px-3 text-xs text-gray-600">{wp?.name ?? "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex justify-between items-center pt-2 border-t border-gray-100">
        <p className="text-sm text-gray-600">
          Vybráno <strong>{selected.size}</strong>
          {filtered.length !== employees.length && (
            <span className="text-xs text-gray-400 ml-2">
              ({filtered.length} viditelných / {employees.length} celkem)
            </span>
          )}
        </p>
        <Button
          onClick={() => assignMutation.mutate([...selected])}
          disabled={selected.size === 0}
          loading={assignMutation.isPending}
        >
          Přiřadit {selected.size > 0 && `(${selected.size})`}
        </Button>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Employee view — Školící centrum
// ════════════════════════════════════════════════════════════════════════════

function EmployeeView() {
  const [detailAssignment, setDetailAssignment] = useState<TrainingAssignment | null>(null);

  const { data: assignments = [], isLoading } = useQuery<TrainingAssignment[]>({
    queryKey: ["my-assignments"],
    queryFn: () => api.get("/trainings/my"),
  });

  return (
    <div>
      <Header title="Školící centrum" />

      <div className="p-6">
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-8 text-sm text-gray-400">Načítám…</div>
            ) : assignments.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <GraduationCap className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Nemáte přiřazená školení</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Školení</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Typ</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Poslední</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-500">Další termín</th>
                    <th className="py-3 px-4" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {assignments.map((a) => (
                    <tr key={a.id} className="hover:bg-gray-50">
                      <td className="py-3 px-4 font-medium text-gray-900">
                        {a.training_title || "—"}
                      </td>
                      <td className="py-3 px-4 text-gray-600 text-xs uppercase">
                        {a.training_type || "—"}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            VALIDITY_COLORS[a.validity_status]
                          )}
                        >
                          {VALIDITY_LABEL[a.validity_status] || a.validity_status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-gray-600">
                        {formatDate(a.last_completed_at)}
                      </td>
                      <td className="py-3 px-4 text-gray-600">
                        {formatDate(a.valid_until)}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center justify-end gap-2">
                          {a.last_completed_at && (
                            <a
                              href={`/api/v1/trainings/assignments/${a.id}/certificate.pdf`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-blue-50 hover:text-blue-600"
                              title="Stáhnout certifikát"
                            >
                              <Award className="h-3.5 w-3.5" />
                              Certifikát
                            </a>
                          )}
                          <Button size="sm" onClick={() => setDetailAssignment(a)}>
                            <PlayCircle className="h-3.5 w-3.5 mr-1" />
                            Otevřít
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={!!detailAssignment}
        onClose={() => setDetailAssignment(null)}
        title={detailAssignment?.training_title || ""}
        size="lg"
      >
        {detailAssignment && (
          <TrainingRunFlow
            assignment={detailAssignment}
            onClose={() => setDetailAssignment(null)}
          />
        )}
      </Dialog>
    </div>
  );
}

// ── Run flow: info → PDF → test → výsledek ──────────────────────────────────

type RunStep = "info" | "pdf" | "test" | "sign" | "result";

function TrainingRunFlow({
  assignment,
  onClose,
}: {
  assignment: TrainingAssignment;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [step, setStep] = useState<RunStep>("info");
  const invalidate = () => qc.invalidateQueries({ queryKey: ["my-assignments"] });

  // Sjednocený flag (#105): pokud školení nevyžaduje ověřený podpis,
  // přeskakujeme krok 'sign' a rovnou jdeme do 'result' — stačí prezenční
  // listina v assignment.last_completed_at.
  const requiresSignature = !!assignment.training_requires_qes;
  const stepAfterCompletion: RunStep = requiresSignature ? "sign" : "result";

  const markReadMutation = useMutation({
    mutationFn: () =>
      api.post<TrainingAssignment>(`/trainings/assignments/${assignment.id}/mark-read`),
    onSuccess: () => {
      invalidate();
      setStep(stepAfterCompletion);
    },
    onError: (err) => {
      // Training má test → přepneme do testu
      if (err instanceof ApiError && err.status === 422) setStep("test");
      else alert(err instanceof ApiError ? err.detail : "Chyba");
    },
  });

  if (step === "info") {
    return (
      <div className="space-y-4">
        <div className="rounded-md bg-blue-50 border border-blue-200 p-4 text-sm">
          <p className="font-medium text-blue-900 mb-1">{assignment.training_title}</p>
          <p className="text-blue-800 text-xs">
            Projděte si obsah školení (PDF). Po dočtení buď potvrdíte absolvování,
            nebo projdete test (pokud je přiložen).
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md border border-gray-200 p-3">
            <p className="text-gray-400">Stav</p>
            <p className="font-medium">{VALIDITY_LABEL[assignment.validity_status]}</p>
          </div>
          <div className="rounded-md border border-gray-200 p-3">
            <p className="text-gray-400">Deadline pro splnění</p>
            <p className="font-medium">{formatDateTime(assignment.deadline)}</p>
          </div>
          <div className="rounded-md border border-gray-200 p-3">
            <p className="text-gray-400">Poslední splnění</p>
            <p className="font-medium">{formatDate(assignment.last_completed_at)}</p>
          </div>
          <div className="rounded-md border border-gray-200 p-3">
            <p className="text-gray-400">Platí do</p>
            <p className="font-medium">{formatDate(assignment.valid_until)}</p>
          </div>
        </div>

        <div className="flex justify-between pt-2 border-t border-gray-100">
          <Button variant="outline" onClick={onClose}>
            Zavřít
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setStep("pdf")}>
              <Eye className="h-4 w-4 mr-1.5" />
              Otevřít školení
            </Button>
            <Button
              onClick={() => markReadMutation.mutate()}
              loading={markReadMutation.isPending}
            >
              <CheckCircle2 className="h-4 w-4 mr-1.5" />
              Ukončit školení
            </Button>
          </div>
        </div>

        {assignment.last_completed_at && (
          <div className="pt-2 border-t border-gray-100">
            <a
              href={`/api/v1/trainings/assignments/${assignment.id}/certificate.pdf`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
            >
              <Award className="h-4 w-4" />
              Stáhnout certifikát
            </a>
          </div>
        )}
      </div>
    );
  }

  if (step === "pdf") {
    return (
      <div className="space-y-3">
        <iframe
          src={`/api/v1/trainings/${assignment.training_id}/content`}
          className="w-full h-[65vh] border border-gray-200 rounded-md"
          title="Obsah školení"
        />
        <div className="flex justify-between">
          <Button variant="outline" onClick={() => setStep("info")}>
            <ChevronLeft className="h-4 w-4 mr-1" />
            Zpět
          </Button>
          <Button
            onClick={() => markReadMutation.mutate()}
            loading={markReadMutation.isPending}
          >
            <CheckCircle2 className="h-4 w-4 mr-1.5" />
            Dočetl jsem — ukončit školení
          </Button>
        </div>
      </div>
    );
  }

  if (step === "test") {
    return (
      <TestTaker
        assignmentId={assignment.id}
        onDone={() => {
          invalidate();
          // Po úspěšném testu — buď podpis (when requires_qes) nebo rovnou výsledek.
          setStep(stepAfterCompletion);
        }}
        onCancel={() => setStep("info")}
      />
    );
  }

  if (step === "sign") {
    return (
      <TrainingSignChoice
        assignment={assignment}
        onCancel={() => setStep("info")}
        onSigned={() => {
          invalidate();
          setStep("result");
        }}
      />
    );
  }

  // result
  return (
    <div className="space-y-4 text-center py-6">
      <CheckCircle2 className="h-14 w-14 text-green-600 mx-auto" />
      <p className="text-lg font-medium text-green-800">Školení splněno</p>
      <p className="text-sm text-gray-600">Certifikát je dostupný v seznamu školení.</p>
      <div className="flex justify-center gap-2 pt-2">
        <a
          href={`/api/v1/trainings/assignments/${assignment.id}/certificate.pdf`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Award className="h-4 w-4" />
          Stáhnout certifikát
        </a>
        <Button variant="outline" onClick={onClose}>
          Zavřít
        </Button>
      </div>
    </div>
  );
}

// ── Test taker: sekvenční otázky ─────────────────────────────────────────────

function TestTaker({
  assignmentId,
  onDone,
  onCancel,
}: {
  assignmentId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [result, setResult] = useState<SubmitTestResponse | null>(null);

  const { data: test, isLoading } = useQuery<StartTestResponse>({
    queryKey: ["test-start", assignmentId],
    queryFn: () => api.post<StartTestResponse>(`/trainings/assignments/${assignmentId}/start`),
  });

  const submitMutation = useMutation({
    mutationFn: () =>
      api.post<SubmitTestResponse>(`/trainings/assignments/${assignmentId}/submit`, {
        answers: Object.entries(answers).map(([idx, text]) => ({
          question_index: Number(idx),
          chosen_answer_text: text,
        })),
      }),
    onSuccess: (res) => setResult(res),
    onError: (err) => alert(err instanceof ApiError ? err.detail : "Odeslání selhalo"),
  });

  if (isLoading || !test) {
    return <div className="py-8 text-center text-sm text-gray-400">Načítám test…</div>;
  }

  if (result) {
    return (
      <div className="space-y-4 text-center py-6">
        {result.passed ? (
          <CheckCircle2 className="h-14 w-14 text-green-600 mx-auto" />
        ) : (
          <XCircle className="h-14 w-14 text-red-600 mx-auto" />
        )}
        <p className="text-lg font-medium">
          {result.passed ? "Test splněn" : "Test nesplněn"}
        </p>
        <p className="text-sm text-gray-600">
          Výsledek: <strong>{result.score_percentage}%</strong> (potřebujete{" "}
          {result.pass_percentage}%)
        </p>
        {!result.passed && (
          <p className="text-xs text-gray-500">Zkuste to znovu — test lze opakovat bez omezení.</p>
        )}
        <div className="flex justify-center gap-2 pt-2">
          {result.passed ? (
            <>
              <a
                href={`/api/v1/trainings/assignments/${assignmentId}/certificate.pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                <Award className="h-4 w-4" />
                Stáhnout certifikát
              </a>
              <Button variant="outline" onClick={onDone}>
                Zavřít
              </Button>
            </>
          ) : (
            <>
              <Button
                onClick={() => {
                  setResult(null);
                  setAnswers({});
                  setCurrentIdx(0);
                }}
              >
                Zkusit znovu
              </Button>
              <Button variant="outline" onClick={onCancel}>
                Zrušit
              </Button>
            </>
          )}
        </div>
      </div>
    );
  }

  const q = test.questions[currentIdx];
  const isLast = currentIdx === test.questions.length - 1;
  const isFirst = currentIdx === 0;
  const allAnswered = test.questions.every((tq) => answers[tq.question_index] !== undefined);
  const selected = answers[q.question_index];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>
          Otázka {currentIdx + 1} z {test.questions.length}
        </span>
        <span>Pro splnění: {test.pass_percentage}%</span>
      </div>

      <div className="rounded-md bg-gray-50 p-4">
        <p className="font-medium text-gray-900 mb-3">{q.question}</p>
        <div className="space-y-2">
          {q.options.map((opt, i) => (
            <label
              key={i}
              className={cn(
                "flex items-start gap-2 rounded-md border px-3 py-2 cursor-pointer transition-colors",
                selected === opt
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:bg-white"
              )}
            >
              <input
                type="radio"
                name={`q_${q.question_index}`}
                checked={selected === opt}
                onChange={() =>
                  setAnswers((prev) => ({ ...prev, [q.question_index]: opt }))
                }
                className="mt-1 h-4 w-4"
              />
              <span className="text-sm flex-1">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="flex justify-between pt-2 border-t border-gray-100">
        <Button
          variant="outline"
          onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
          disabled={isFirst}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Předchozí
        </Button>

        {isLast ? (
          <Button
            onClick={() => submitMutation.mutate()}
            disabled={!allAnswered}
            loading={submitMutation.isPending}
          >
            <FileUp className="h-4 w-4 mr-1.5" />
            Odeslat test
          </Button>
        ) : (
          <Button
            onClick={() => setCurrentIdx((i) => i + 1)}
            disabled={selected === undefined}
          >
            Další
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        )}
      </div>

      {!allAnswered && isLast && (
        <p className="text-xs text-amber-600 text-right">
          Pro odeslání odpovězte na všechny otázky.
        </p>
      )}
    </div>
  );
}
