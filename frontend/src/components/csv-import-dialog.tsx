"use client";

/**
 * Generický CSV import dialog. Použito pro import zaměstnanců i revizí.
 *
 * Volající dodá:
 * - title (např. "Import zaměstnanců z CSV")
 * - templateUrl (např. "/api/v1/employees/import/template")
 * - uploadEndpoint (např. "/employees/import")
 * - requirements (text seznam pravidel pro CSV)
 *
 * Komponenta volá uploadFile<TResult>() — `TResult` musí mít fields
 * `total_rows`, `created_count`, `failed_count`, `rows: { row_index, success, error?, title? }[]`.
 */

import { useState } from "react";
import { Download, Upload, FileText, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { ApiError, uploadFile } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";

export interface ImportRowResult {
  row_index: number;
  success: boolean;
  error: string | null;
  title?: string | null;
}

export interface ImportResult {
  total_rows: number;
  created_count: number;
  failed_count: number;
  rows: ImportRowResult[];
}

export function CsvImportDialog({
  open,
  onClose,
  onImported,
  title,
  templateUrl,
  uploadEndpoint,
  requirements,
}: {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  title: string;
  templateUrl: string;
  uploadEndpoint: string;
  requirements: React.ReactNode;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file) return;
    setError(null);
    setIsUploading(true);
    try {
      const res = await uploadFile<ImportResult>(uploadEndpoint, file);
      setResult(res);
      if (res.created_count > 0) onImported();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Nahrávání selhalo");
    } finally {
      setIsUploading(false);
    }
  }

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} title={title} size="lg">
      {!result ? (
        <div className="space-y-5">
          <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
            <div className="flex items-start gap-3">
              <FileText className="h-5 w-5 shrink-0 text-blue-600 mt-0.5" />
              <div className="flex-1 text-sm">
                <p className="font-medium text-blue-900">Nemáte připravený soubor?</p>
                <p className="mt-1 text-blue-800">
                  Stáhněte vzorový CSV s přesnou hlavičkou a příklady.
                  Otevřete v Excelu, doplňte data a nahrajte zpět.
                </p>
              </div>
              <Button
                variant="outline" size="sm"
                onClick={() => window.open(templateUrl, "_blank")}
              >
                <Download className="h-3.5 w-3.5 mr-1" />
                Vzor CSV
              </Button>
            </div>
          </div>

          <div className="text-xs text-gray-600">
            {requirements}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="csv_file">Vyberte CSV soubor</Label>
            <input
              id="csv_file"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
            />
            {file && (
              <p className="text-xs text-gray-500">
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>

          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
            <Button variant="outline" onClick={handleClose}>Zrušit</Button>
            <Button onClick={submit} disabled={!file} loading={isUploading}>
              <Upload className="h-4 w-4 mr-1.5" />
              Importovat
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary banner */}
          <div className="rounded-md border bg-gray-50 px-4 py-3">
            <div className="flex items-center gap-3">
              {result.failed_count === 0 ? (
                <CheckCircle className="h-6 w-6 text-green-600" />
              ) : result.created_count === 0 ? (
                <XCircle className="h-6 w-6 text-red-600" />
              ) : (
                <AlertTriangle className="h-6 w-6 text-amber-600" />
              )}
              <div className="flex-1">
                <p className="font-semibold text-gray-900">
                  Importováno {result.created_count} z {result.total_rows} řádků
                </p>
                {result.failed_count > 0 && (
                  <p className="text-sm text-red-700">
                    {result.failed_count} řádků selhalo — viz níže.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Failed rows */}
          {result.rows.some((r) => !r.success) && (
            <div className="border border-red-200 rounded-md max-h-72 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-red-50 sticky top-0">
                  <tr>
                    <th className="text-left py-2 px-3 font-medium text-red-800">Řádek</th>
                    <th className="text-left py-2 px-3 font-medium text-red-800">Chyba</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-red-100">
                  {result.rows.filter((r) => !r.success).map((r) => (
                    <tr key={r.row_index} className="hover:bg-red-50/50">
                      <td className="py-2 px-3 text-red-700 font-mono">{r.row_index}</td>
                      <td className="py-2 px-3 text-red-700">{r.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
            <Button variant="outline" onClick={reset}>Importovat další</Button>
            <Button onClick={handleClose}>Hotovo</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
