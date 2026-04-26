"use client";

/**
 * Editor testových otázek pro Training šablonu.
 *
 * Layout:
 *  - Seznam otázek (přidat / smazat / posunout)
 *  - Per otázku: text + 4 možnosti (1 správná, 3 chybné)
 *  - Pass percentage (0-100)
 *  - Validace: aspoň 1 otázka, každá má všechna pole, žádné duplicity odpovědí
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ArrowUp, ArrowDown, CheckCircle2, AlertCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface TestQuestion {
  question: string;
  correct_answer: string;
  wrong_answers: string[];  // přesně 3
}

interface TestPayload {
  questions: TestQuestion[];
  pass_percentage: number | null;
}

function emptyQuestion(): TestQuestion {
  return { question: "", correct_answer: "", wrong_answers: ["", "", ""] };
}

function validateQuestions(qs: TestQuestion[]): string | null {
  if (qs.length === 0) return "Přidej alespoň jednu otázku.";
  for (let i = 0; i < qs.length; i++) {
    const q = qs[i];
    const labelPrefix = `Otázka ${i + 1}: `;
    if (!q.question.trim()) return labelPrefix + "chybí text otázky.";
    if (!q.correct_answer.trim()) return labelPrefix + "chybí správná odpověď.";
    if (q.wrong_answers.some((w) => !w.trim()))
      return labelPrefix + "všechny 3 chybné odpovědi musí být vyplněné.";
    const all = [q.correct_answer.trim(), ...q.wrong_answers.map((w) => w.trim())];
    const uniq = new Set(all.map((a) => a.toLowerCase()));
    if (uniq.size !== 4)
      return labelPrefix + "odpovědi se nesmí opakovat.";
  }
  return null;
}

export function TestQuestionsDialog({
  open,
  onClose,
  trainingId,
  trainingTitle,
}: {
  open: boolean;
  onClose: () => void;
  trainingId: string | null;
  trainingTitle: string;
}) {
  const qc = useQueryClient();
  const [questions, setQuestions] = useState<TestQuestion[]>([]);
  const [passPercentage, setPassPercentage] = useState<number>(80);
  const [validationError, setValidationError] = useState<string | null>(null);

  const { data, isLoading } = useQuery<TestPayload>({
    queryKey: ["training-test", trainingId],
    queryFn: () => api.get(`/trainings/${trainingId}/test/json`),
    enabled: open && !!trainingId,
  });

  useEffect(() => {
    if (data) {
      setQuestions(data.questions.length ? data.questions : [emptyQuestion()]);
      setPassPercentage(data.pass_percentage ?? 80);
    } else if (open && !isLoading) {
      setQuestions([emptyQuestion()]);
      setPassPercentage(80);
    }
  }, [data, open, isLoading]);

  const saveMutation = useMutation({
    mutationFn: () =>
      api.put(`/trainings/${trainingId}/test/json`, {
        questions,
        pass_percentage: passPercentage,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trainings"] });
      qc.invalidateQueries({ queryKey: ["training-test", trainingId] });
      setValidationError(null);
      onClose();
    },
    onError: (err) =>
      setValidationError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function addQuestion() {
    setQuestions([...questions, emptyQuestion()]);
  }
  function removeQuestion(i: number) {
    setQuestions(questions.filter((_, idx) => idx !== i));
  }
  function moveQuestion(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= questions.length) return;
    const next = [...questions];
    [next[i], next[j]] = [next[j], next[i]];
    setQuestions(next);
  }
  function updateQuestion(i: number, patch: Partial<TestQuestion>) {
    setQuestions(questions.map((q, idx) => (idx === i ? { ...q, ...patch } : q)));
  }
  function updateWrong(i: number, w: number, value: string) {
    setQuestions(
      questions.map((q, idx) =>
        idx === i
          ? { ...q, wrong_answers: q.wrong_answers.map((x, k) => (k === w ? value : x)) }
          : q,
      ),
    );
  }

  function handleSave() {
    const err = validateQuestions(questions);
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError(null);
    saveMutation.mutate();
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Test otázky — ${trainingTitle}`} size="lg">
      {isLoading ? (
        <div className="h-40 animate-pulse bg-gray-50 rounded" />
      ) : (
        <div className="space-y-4">
          {/* Pass percentage */}
          <div className="rounded-md border border-blue-200 bg-blue-50 p-3 flex items-end gap-3">
            <div className="space-y-1.5 flex-1">
              <Label htmlFor="pass-pct">Procento pro úspěch *</Label>
              <Input
                id="pass-pct"
                type="number"
                min="0"
                max="100"
                value={passPercentage}
                onChange={(e) => setPassPercentage(parseInt(e.target.value, 10) || 0)}
              />
              <p className="text-xs text-blue-800">
                Zaměstnanec musí dosáhnout alespoň tohoto skóre (0–100 %).
                Doporučujeme 80 % nebo více.
              </p>
            </div>
            <div className="text-xs text-gray-500 pb-2">
              Otázek: <strong>{questions.length}</strong>
            </div>
          </div>

          {/* Otázky */}
          <div className="space-y-3 max-h-[55vh] overflow-y-auto pr-1">
            {questions.map((q, i) => (
              <div
                key={i}
                className="rounded-md border border-gray-200 bg-white p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-500">
                    Otázka {i + 1}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => moveQuestion(i, -1)}
                      disabled={i === 0}
                      className="rounded p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
                      title="Posunout nahoru"
                    >
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveQuestion(i, 1)}
                      disabled={i === questions.length - 1}
                      className="rounded p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
                      title="Posunout dolů"
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeQuestion(i)}
                      disabled={questions.length === 1}
                      className="rounded p-1 text-gray-400 hover:text-red-600 disabled:opacity-30"
                      title="Smazat otázku"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={`q-${i}`}>Text otázky</Label>
                  <textarea
                    id={`q-${i}`}
                    value={q.question}
                    onChange={(e) => updateQuestion(i, { question: e.target.value })}
                    rows={2}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                    placeholder="Co je první pomoc při poranění hlavy?"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={`correct-${i}`} className="flex items-center gap-1.5 text-green-700">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Správná odpověď
                  </Label>
                  <Input
                    id={`correct-${i}`}
                    value={q.correct_answer}
                    onChange={(e) => updateQuestion(i, { correct_answer: e.target.value })}
                    className="border-green-300 bg-green-50"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-gray-600">Chybné odpovědi (3×)</Label>
                  {q.wrong_answers.map((w, wi) => (
                    <Input
                      key={wi}
                      value={w}
                      onChange={(e) => updateWrong(i, wi, e.target.value)}
                      placeholder={`Chybná odpověď ${wi + 1}`}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" onClick={addQuestion}>
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat otázku
          </Button>

          {validationError && (
            <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{validationError}</span>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
            <Button variant="outline" onClick={onClose}>Zrušit</Button>
            <Button
              loading={saveMutation.isPending}
              onClick={handleSave}
            >
              Uložit test
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
