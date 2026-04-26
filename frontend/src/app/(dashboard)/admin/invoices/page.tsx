"use client";

/**
 * Platform admin — všechny faktury napříč tenanty.
 * Filtry, akce: download PDF, resend email, mark paid, cancel, run-monthly cron.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Receipt, Download, Send, Loader2, AlertCircle, CheckCircle2,
  Clock, FileText, Play, X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import {
  type InvoiceListItem,
  type InvoiceStatus,
  INVOICE_STATUS_LABELS,
} from "@/types/api";

interface TenantOverviewItem {
  id: string;
  name: string;
  billing_company_name: string | null;
}

interface RunMonthlyResponse {
  generated_count: number;
  invoice_numbers: string[];
  delivered_count: number;
}

const STATUS_STYLES: Record<InvoiceStatus, { bg: string; text: string; Icon: typeof CheckCircle2 }> = {
  draft:     { bg: "bg-gray-100",   text: "text-gray-700",   Icon: FileText },
  sent:      { bg: "bg-blue-100",   text: "text-blue-700",   Icon: Clock },
  paid:      { bg: "bg-green-100",  text: "text-green-700",  Icon: CheckCircle2 },
  cancelled: { bg: "bg-red-100",    text: "text-red-700",    Icon: AlertCircle },
};

const SELECT_CLS = "rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("cs-CZ");
}

function formatAmount(value: string, currency: string): string {
  return `${parseFloat(value).toLocaleString("cs-CZ", { minimumFractionDigits: 2 })} ${currency}`;
}

function StatusBadge({ status }: { status: InvoiceStatus }) {
  const { bg, text, Icon } = STATUS_STYLES[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${bg} ${text}`}>
      <Icon className="h-3 w-3" />
      {INVOICE_STATUS_LABELS[status]}
    </span>
  );
}

export default function AdminInvoicesPage() {
  const qc = useQueryClient();
  const [filterTenant, setFilterTenant] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<InvoiceStatus | "">("");

  const { data: invoices = [], isLoading } = useQuery<InvoiceListItem[]>({
    queryKey: ["admin-invoices", filterTenant, filterStatus],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filterTenant) params.set("tenant_id", filterTenant);
      if (filterStatus) params.set("invoice_status", filterStatus);
      const qs = params.toString();
      return api.get(`/admin/invoices${qs ? "?" + qs : ""}`);
    },
  });

  const { data: tenantOverview } = useQuery<{ tenants: TenantOverviewItem[] }>({
    queryKey: ["admin-tenant-overview-list"],
    queryFn: () => api.get("/admin/tenant-overview"),
    staleTime: 60 * 1000,
  });

  const tenantsById = new Map<string, string>(
    (tenantOverview?.tenants ?? []).map(t => [t.id, t.billing_company_name ?? t.name]),
  );

  const markPaidMutation = useMutation({
    mutationFn: (id: string) => api.patch(`/admin/invoices/${id}`, { status: "paid" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invoices"] }),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.patch(`/admin/invoices/${id}`, { status: "cancelled" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invoices"] }),
  });

  const sendEmailMutation = useMutation<{ sent_to: string }, ApiError, string>({
    mutationFn: (id) => api.post<{ sent_to: string }>(`/admin/invoices/${id}/send`, {}),
    onSuccess: (data) => {
      alert(`Faktura odeslána na ${data.sent_to}`);
      qc.invalidateQueries({ queryKey: ["admin-invoices"] });
    },
    onError: (err) => {
      alert(err.detail || "Odeslání selhalo");
    },
  });

  const runMonthlyMutation = useMutation<RunMonthlyResponse, ApiError, void>({
    mutationFn: () => api.post<RunMonthlyResponse>("/admin/invoices/run-monthly?deliver=true", {}),
    onSuccess: (data) => {
      alert(
        `Vystaveno ${data.generated_count} faktur, doručeno ${data.delivered_count}.\n\n` +
        (data.invoice_numbers.length > 0
          ? "Čísla: " + data.invoice_numbers.join(", ")
          : "Žádné nové faktury (možná jsi už dnes spustil cron)."),
      );
      qc.invalidateQueries({ queryKey: ["admin-invoices"] });
    },
    onError: (err) => alert(err.detail || "Cron selhal"),
  });

  const handleDownload = async (invoice: InvoiceListItem) => {
    const resp = await fetch(`/api/v1/admin/invoices/${invoice.id}/pdf`);
    if (!resp.ok) {
      alert("Stažení selhalo");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `faktura_${invoice.invoice_number}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const totalSum = invoices
    .filter(i => i.status !== "cancelled")
    .reduce((acc, i) => acc + parseFloat(i.total), 0);
  const paidSum = invoices
    .filter(i => i.status === "paid")
    .reduce((acc, i) => acc + parseFloat(i.total), 0);
  const pendingSum = invoices
    .filter(i => i.status === "sent" || i.status === "draft")
    .reduce((acc, i) => acc + parseFloat(i.total), 0);

  return (
    <div>
      <Header
        title="Faktury (všichni zákazníci)"
        actions={
          <Button
            size="sm"
            onClick={() => {
              if (confirm("Spustit měsíční cron? Vystaví a pošle faktury všem aktivním tenantům za předchozí měsíc.")) {
                runMonthlyMutation.mutate();
              }
            }}
            loading={runMonthlyMutation.isPending}
          >
            <Play className="h-4 w-4 mr-1.5" /> Spustit měsíční cron
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Souhrn */}
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Celkem (bez storno)</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">
                {totalSum.toLocaleString("cs-CZ", { minimumFractionDigits: 2 })} CZK
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Čeká na úhradu</div>
              <div className="mt-1 text-2xl font-bold text-blue-700">
                {pendingSum.toLocaleString("cs-CZ", { minimumFractionDigits: 2 })} CZK
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Zaplaceno</div>
              <div className="mt-1 text-2xl font-bold text-green-700">
                {paidSum.toLocaleString("cs-CZ", { minimumFractionDigits: 2 })} CZK
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filtry */}
        <Card>
          <CardContent className="p-4 flex flex-wrap items-center gap-3">
            <span className="text-sm font-semibold text-gray-700">Filtr:</span>
            <select
              value={filterTenant}
              onChange={(e) => setFilterTenant(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">Všichni zákazníci</option>
              {(tenantOverview?.tenants ?? []).map(t => (
                <option key={t.id} value={t.id}>{t.billing_company_name ?? t.name}</option>
              ))}
            </select>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as InvoiceStatus | "")}
              className={SELECT_CLS}
            >
              <option value="">Všechny stavy</option>
              <option value="draft">Koncept</option>
              <option value="sent">Odeslána</option>
              <option value="paid">Zaplaceno</option>
              <option value="cancelled">Storno</option>
            </select>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Načítám…
              </div>
            ) : invoices.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Receipt className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné faktury</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Číslo</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Zákazník</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Vystavena</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Splatnost</th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">Částka</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {invoices.map(inv => (
                      <tr key={inv.id} className="hover:bg-gray-50">
                        <td className="py-3 px-4 font-medium text-gray-900">{inv.invoice_number}</td>
                        <td className="py-3 px-4 text-gray-700">
                          {tenantsById.get(inv.tenant_id) ?? inv.tenant_id.slice(0, 8)}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(inv.issued_at)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(inv.due_date)}</td>
                        <td className="py-3 px-4 text-right font-bold text-gray-900">
                          {formatAmount(inv.total, inv.currency)}
                        </td>
                        <td className="py-3 px-4">
                          <StatusBadge status={inv.status} />
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Tooltip label="Stáhnout PDF">
                              <button
                                onClick={() => handleDownload(inv)}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                aria-label="PDF"
                              >
                                <Download className="h-4 w-4" />
                              </button>
                            </Tooltip>
                            <Tooltip label="Poslat emailem">
                              <button
                                onClick={() => sendEmailMutation.mutate(inv.id)}
                                disabled={sendEmailMutation.isPending}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 disabled:opacity-30"
                                aria-label="Poslat"
                              >
                                <Send className="h-4 w-4" />
                              </button>
                            </Tooltip>
                            {inv.status !== "paid" && inv.status !== "cancelled" && (
                              <Tooltip label="Označit zaplaceno">
                                <button
                                  onClick={() => markPaidMutation.mutate(inv.id)}
                                  className="rounded p-1 text-gray-400 hover:text-green-600 hover:bg-green-50"
                                  aria-label="Mark paid"
                                >
                                  <CheckCircle2 className="h-4 w-4" />
                                </button>
                              </Tooltip>
                            )}
                            {inv.status !== "cancelled" && (
                              <Tooltip label="Storno">
                                <button
                                  onClick={() => {
                                    if (confirm(`Stornovat fakturu ${inv.invoice_number}?`))
                                      cancelMutation.mutate(inv.id);
                                  }}
                                  className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                                  aria-label="Storno"
                                >
                                  <X className="h-4 w-4" />
                                </button>
                              </Tooltip>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="rounded-md bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800">
          <strong>Tip:</strong> &bdquo;Spustit měsíční cron&ldquo; vystaví faktury za předchozí měsíc
          všem aktivním tenantům s billing_type monthly/yearly/per_employee.
          Pro custom billing musíš fakturu vystavit ručně přes API.
        </div>
      </div>
    </div>
  );
}
