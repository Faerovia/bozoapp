"use client";

/**
 * Tenant Fakturace — vlastní faktury (RLS-isolated).
 * OZO/HR vidí historii faktur, status, download PDF.
 */

import { useQuery } from "@tanstack/react-query";
import {
  Receipt, Download, Loader2, AlertCircle, CheckCircle2,
  Clock, FileText,
} from "lucide-react";
import { api } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import {
  type InvoiceListItem,
  type InvoiceStatus,
  INVOICE_STATUS_LABELS,
} from "@/types/api";

const STATUS_STYLES: Record<InvoiceStatus, { bg: string; text: string; Icon: typeof CheckCircle2 }> = {
  draft:     { bg: "bg-gray-100",   text: "text-gray-700",   Icon: FileText },
  sent:      { bg: "bg-blue-100",   text: "text-blue-700",   Icon: Clock },
  paid:      { bg: "bg-green-100",  text: "text-green-700",  Icon: CheckCircle2 },
  cancelled: { bg: "bg-red-100",    text: "text-red-700",    Icon: AlertCircle },
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("cs-CZ");
}

function formatAmount(value: string, currency: string): string {
  const num = parseFloat(value);
  return `${num.toLocaleString("cs-CZ", { minimumFractionDigits: 2 })} ${currency}`;
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

function isOverdue(invoice: InvoiceListItem): boolean {
  if (invoice.status === "paid" || invoice.status === "cancelled") return false;
  return new Date(invoice.due_date) < new Date();
}

export default function BillingPage() {
  const { data: invoices = [], isLoading, isError } = useQuery<InvoiceListItem[]>({
    queryKey: ["my-invoices"],
    queryFn: () => api.get("/billing/invoices"),
  });

  const handleDownload = async (invoice: InvoiceListItem) => {
    const resp = await fetch(`/api/v1/billing/invoices/${invoice.id}/pdf`);
    if (!resp.ok) {
      alert("Stažení faktury selhalo.");
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

  // Agregace pro mini-statistiku
  const stats = {
    total: invoices.length,
    pending: invoices.filter(i => i.status === "sent" || i.status === "draft").length,
    overdue: invoices.filter(isOverdue).length,
    paid: invoices.filter(i => i.status === "paid").length,
  };

  if (isError) {
    return (
      <div>
        <Header title="Fakturace" />
        <div className="p-6">
          <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            Faktury se nepodařilo načíst.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header title="Fakturace" />

      <div className="p-6 space-y-4">
        {/* Mini stat panel */}
        <div className="grid grid-cols-4 gap-3">
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Celkem faktur</div>
              <div className="mt-1 text-2xl font-bold text-gray-900">{stats.total}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Čekající úhrada</div>
              <div className="mt-1 text-2xl font-bold text-blue-700">{stats.pending}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Po splatnosti</div>
              <div className={`mt-1 text-2xl font-bold ${stats.overdue > 0 ? "text-red-700" : "text-gray-400"}`}>
                {stats.overdue}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs text-gray-500">Zaplaceno</div>
              <div className="mt-1 text-2xl font-bold text-green-700">{stats.paid}</div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Načítám…
              </div>
            ) : invoices.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Receipt className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Zatím žádné faktury</p>
                <p className="text-xs mt-1">První faktura ti přijde 1. dne dalšího měsíce.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Číslo</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Vystavena</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Splatnost</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Období</th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">Částka</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {invoices.map(inv => (
                      <tr key={inv.id} className="hover:bg-gray-50">
                        <td className="py-3 px-4 font-medium text-gray-900">{inv.invoice_number}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(inv.issued_at)}</td>
                        <td className={`py-3 px-4 ${isOverdue(inv) ? "text-red-700 font-semibold" : "text-gray-600"}`}>
                          {formatDate(inv.due_date)}
                          {isOverdue(inv) && <span className="ml-1 text-xs">(po splatnosti)</span>}
                        </td>
                        <td className="py-3 px-4 text-xs text-gray-500">
                          {formatDate(inv.period_from)} – {formatDate(inv.period_to)}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-gray-900">
                          {formatAmount(inv.total, inv.currency)}
                        </td>
                        <td className="py-3 px-4">
                          <StatusBadge status={inv.status} />
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Tooltip label="Stáhnout PDF">
                            <button
                              onClick={() => handleDownload(inv)}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                              aria-label="Stáhnout PDF"
                            >
                              <Download className="h-4 w-4" />
                            </button>
                          </Tooltip>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          Faktura ti chodí emailem 1. dne každého měsíce. Pokud nemáš poslední fakturu,
          zkontroluj spam, případně kontaktuj fakturace@bozoapp.cz.
        </div>
      </div>
    </div>
  );
}
