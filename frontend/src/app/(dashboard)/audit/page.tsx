"use client";

/**
 * Audit log — read-only přehled změn v tenantu.
 *
 * Filtry: action (CREATE/UPDATE/DELETE/VIEW/EXPORT), resource_type, user.
 * Klik na řádek → expand JSON diff (old_values / new_values).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, ChevronDown, ChevronRight, Filter, FileJson, RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Action = "CREATE" | "UPDATE" | "DELETE" | "VIEW" | "EXPORT";

interface AuditLogItem {
  id: number;
  tenant_id: string;
  user_id: string | null;
  user_email: string | null;
  user_full_name: string | null;
  action: Action;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  created_at: string;
  has_diff: boolean;
}

interface AuditLogDetail extends AuditLogItem {
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  user_agent: string | null;
}

const ACTION_COLORS: Record<Action, string> = {
  CREATE: "bg-green-100 text-green-700",
  UPDATE: "bg-blue-100 text-blue-700",
  DELETE: "bg-red-100 text-red-700",
  VIEW:   "bg-gray-100 text-gray-600",
  EXPORT: "bg-purple-100 text-purple-700",
};

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function ExpandedRow({ id }: { id: number }) {
  const { data, isLoading } = useQuery<AuditLogDetail>({
    queryKey: ["audit-detail", id],
    queryFn: () => api.get(`/audit/${id}`),
  });

  if (isLoading) {
    return <div className="px-4 py-3 text-xs text-gray-400">Načítám…</div>;
  }
  if (!data) return null;

  return (
    <div className="px-6 py-3 bg-gray-50 border-t border-gray-100 space-y-2">
      {data.user_agent && (
        <div className="text-xs text-gray-600">
          <span className="font-medium text-gray-500">User-Agent:</span> {data.user_agent}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs font-medium text-red-600 mb-1">Old values</p>
          <pre className="text-[10px] bg-white border border-red-100 rounded p-2 overflow-auto max-h-64">
            {data.old_values ? JSON.stringify(data.old_values, null, 2) : "—"}
          </pre>
        </div>
        <div>
          <p className="text-xs font-medium text-green-600 mb-1">New values</p>
          <pre className="text-[10px] bg-white border border-green-100 rounded p-2 overflow-auto max-h-64">
            {data.new_values ? JSON.stringify(data.new_values, null, 2) : "—"}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function AuditLogPage() {
  const [action, setAction] = useState<string>("");
  const [resourceType, setResourceType] = useState<string>("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data: items = [], isLoading, refetch } = useQuery<AuditLogItem[]>({
    queryKey: ["audit", action, resourceType],
    queryFn: () => {
      const p = new URLSearchParams();
      if (action) p.set("action", action);
      if (resourceType) p.set("resource_type", resourceType);
      p.set("limit", "200");
      return api.get(`/audit?${p.toString()}`);
    },
  });

  function fmt(s: string) {
    return new Date(s).toLocaleString("cs-CZ");
  }

  return (
    <div>
      <Header
        title="Audit log"
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Obnovit
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end bg-gray-50 border border-gray-200 rounded-md p-3">
          <div>
            <Label htmlFor="f-action" className="text-xs text-gray-600 flex items-center gap-1">
              <Filter className="h-3 w-3" /> Akce
            </Label>
            <select
              id="f-action"
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">Všechny</option>
              <option value="CREATE">CREATE</option>
              <option value="UPDATE">UPDATE</option>
              <option value="DELETE">DELETE</option>
              <option value="VIEW">VIEW</option>
              <option value="EXPORT">EXPORT</option>
            </select>
          </div>
          <div>
            <Label htmlFor="f-rt" className="text-xs text-gray-600">Typ entity</Label>
            <Input
              id="f-rt"
              value={resourceType}
              onChange={(e) => setResourceType(e.target.value)}
              placeholder="employees, trainings, revisions, ..."
            />
          </div>
          <div className="text-xs text-gray-500 pb-2 text-right">
            {items.length} záznamů
          </div>
        </div>

        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 text-sm text-gray-400">Načítám…</div>
            ) : items.length === 0 ? (
              <div className="py-12 text-center text-gray-400">
                <Activity className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">Žádné audit záznamy</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-2 px-3 text-xs font-medium text-gray-500 w-8" />
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Kdy</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Kdo</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Akce</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Entita</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">ID</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">IP</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {items.map((it) => {
                      const open = expandedId === it.id;
                      return (
                        <>
                          <tr
                            key={it.id}
                            onClick={() => setExpandedId(open ? null : it.id)}
                            className={cn(
                              "cursor-pointer transition-colors",
                              open ? "bg-blue-50/50" : "hover:bg-gray-50",
                            )}
                          >
                            <td className="py-2 px-3 text-gray-400">
                              {it.has_diff ? (
                                open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />
                              ) : (
                                <span className="text-gray-300">—</span>
                              )}
                            </td>
                            <td className="py-2 px-4 text-gray-700 text-xs whitespace-nowrap">
                              {fmt(it.created_at)}
                            </td>
                            <td className="py-2 px-4 text-gray-700 text-xs">
                              {it.user_full_name || it.user_email || "—"}
                            </td>
                            <td className="py-2 px-4">
                              <span className={cn(
                                "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase",
                                ACTION_COLORS[it.action] ?? "bg-gray-100 text-gray-600",
                              )}>
                                {it.action}
                              </span>
                            </td>
                            <td className="py-2 px-4 text-gray-700 text-xs font-mono">
                              {it.resource_type}
                            </td>
                            <td className="py-2 px-4 text-gray-500 text-[10px] font-mono">
                              {it.resource_id ? it.resource_id.slice(0, 8) + "…" : "—"}
                            </td>
                            <td className="py-2 px-4 text-gray-500 text-xs font-mono">
                              {it.ip_address || "—"}
                            </td>
                          </tr>
                          {open && it.has_diff && (
                            <tr key={`${it.id}-detail`}>
                              <td colSpan={7} className="p-0">
                                <ExpandedRow id={it.id} />
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800 flex items-start gap-2">
          <FileJson className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>
            Audit log je <strong>append-only</strong> — záznamy nelze upravit ani smazat.
            Změny se zachycují automaticky při každé operaci v aplikaci.
          </span>
        </div>
      </div>
    </div>
  );
}
