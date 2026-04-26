/**
 * Offline write queue (PWA).
 *
 * Strategie:
 *   1. Při POST/PUT/PATCH na cílový endpoint zkontroluj `navigator.onLine`.
 *   2. Pokud online → standardní fetch.
 *   3. Pokud offline → ulož request do IndexedDB queue + vrať syntetický
 *      response (status 202 + custom flag).
 *   4. Při události `online` se queue automaticky vyprázdní (replay).
 *
 * Limitations (MVP):
 *   - Nezvládá race conditions když server vrátí 4xx/5xx pro replayed request
 *     (stačí logovat a držet v queue se status=failed).
 *   - GET requesty se NEcacheují — uživatel nemá offline data k zobrazení.
 *     Pro plné offline-first je třeba i SW cache strategie pro list endpointy.
 *   - Auth: cookie httpOnly nelze přečíst z JS, ale prohlížeč ji pošle při
 *     replay automaticky pokud je stále valid. Po expiraci 401 → user musí
 *     znovu přihlásit a queue se zachová.
 *
 * Použití:
 *   import { queueOrSend } from "@/lib/offline-queue";
 *   await queueOrSend("POST", "/operating-logs/devices/{id}/entries", payload);
 *
 * Status:
 *   Tato implementace je MVP scaffold — produkčně otestovat replay logiku
 *   a edge cases (expirovaný token, 4xx response, conflict resolution).
 */

const DB_NAME = "digitalozo_offline_v1";
const STORE = "queue";

interface QueueEntry {
  id?: number;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  body: unknown;
  created_at: string;
  attempts: number;
  last_error?: string;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => Promise<T> | T,
): Promise<T> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const store = tx.objectStore(STORE);
    Promise.resolve(fn(store)).then(resolve, reject);
    tx.onerror = () => reject(tx.error);
  });
}

export async function enqueue(
  method: QueueEntry["method"],
  url: string,
  body: unknown,
): Promise<void> {
  await withStore("readwrite", (store) => {
    return new Promise<void>((resolve) => {
      const req = store.add({
        method, url, body,
        created_at: new Date().toISOString(),
        attempts: 0,
      } as QueueEntry);
      req.onsuccess = () => resolve();
    });
  });
}

export async function listQueue(): Promise<QueueEntry[]> {
  return withStore("readonly", (store) => {
    return new Promise<QueueEntry[]>((resolve) => {
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result as QueueEntry[]);
    });
  });
}

export async function removeEntry(id: number): Promise<void> {
  await withStore("readwrite", (store) => {
    return new Promise<void>((resolve) => {
      const req = store.delete(id);
      req.onsuccess = () => resolve();
    });
  });
}

/**
 * Replay všech queue entries. Zavolat při `online` eventu nebo manuálně.
 * Vrátí počet úspěšně synced + počet selhání.
 */
export async function replayQueue(): Promise<{ ok: number; failed: number }> {
  const entries = await listQueue();
  let ok = 0;
  let failed = 0;
  for (const e of entries) {
    try {
      const resp = await fetch(`/api/v1${e.url}`, {
        method: e.method,
        headers: { "Content-Type": "application/json" },
        body: e.body ? JSON.stringify(e.body) : undefined,
        credentials: "same-origin",
      });
      if (resp.ok) {
        if (e.id !== undefined) await removeEntry(e.id);
        ok += 1;
      } else {
        failed += 1;
      }
    } catch {
      failed += 1;
    }
  }
  return { ok, failed };
}

/**
 * Hlavní helper: pokud online → normální fetch; pokud offline → enqueue
 * a vrátí syntetický 'queued' result.
 */
export async function queueOrSend<T = unknown>(
  method: QueueEntry["method"],
  url: string,
  body: unknown,
): Promise<{ queued: true } | { queued: false; data: T }> {
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    await enqueue(method, url, body);
    return { queued: true };
  }
  const resp = await fetch(`/api/v1${url}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  const data = (await resp.json()) as T;
  return { queued: false, data };
}

/**
 * Auto-replay setup — zaregistruje listener na `online` event.
 * Volat jednou v root komponentě.
 */
export function setupAutoReplay(
  onSync?: (result: { ok: number; failed: number }) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = async () => {
    const result = await replayQueue();
    if (onSync) onSync(result);
  };
  window.addEventListener("online", handler);
  return () => window.removeEventListener("online", handler);
}
