"use client";

/**
 * PWA install banner.
 *
 * - Android/desktop Chrome: zachytí `beforeinstallprompt` event a ukáže button
 * - iOS Safari: zobrazí návod "Přidat na plochu" (iOS install prompt API neexistuje)
 *
 * Banner zmizí po:
 * - úspěšné instalaci
 * - kliku na "Zavřít" (uložené v sessionStorage — nezobrazí se v dané session znovu)
 * - když je app už spuštěná v standalone módu
 */

import { useEffect, useState } from "react";
import { X, Smartphone } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_KEY = "bozoapp_install_prompt_dismissed";

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS PWA detect
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

function isIOSSafari(): boolean {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua);
  const isWebKit = /WebKit/.test(ua);
  const isCriOS = /CriOS/.test(ua);  // Chrome on iOS
  const isFxiOS = /FxiOS/.test(ua);  // Firefox on iOS
  return isIOS && isWebKit && !isCriOS && !isFxiOS;
}

export function PWAInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIOSHint, setShowIOSHint] = useState(false);
  const [dismissed, setDismissed] = useState(true);  // default skrytý

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (isStandalone()) return;
    if (sessionStorage.getItem(DISMISS_KEY) === "1") return;

    setDismissed(false);

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // iOS — žádný native event, ale zobrazíme hint po malé prodlevě (3s)
    if (isIOSSafari()) {
      const t = setTimeout(() => setShowIOSHint(true), 3000);
      return () => {
        clearTimeout(t);
        window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      };
    }

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    if (choice.outcome === "accepted" || choice.outcome === "dismissed") {
      setDeferredPrompt(null);
      sessionStorage.setItem(DISMISS_KEY, "1");
      setDismissed(true);
    }
  };

  const handleDismiss = () => {
    sessionStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
    setShowIOSHint(false);
  };

  if (dismissed) return null;
  if (!deferredPrompt && !showIOSHint) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:max-w-sm z-50 rounded-lg border border-blue-200 bg-blue-50 p-4 shadow-lg">
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-blue-600 p-2 text-white">
          <Smartphone className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-blue-900">
            Nainstalovat BOZOapp
          </p>
          {deferredPrompt ? (
            <p className="mt-1 text-xs text-blue-800">
              Přidej si BOZOapp na plochu pro rychlejší přístup a podporu offline režimu.
            </p>
          ) : (
            <p className="mt-1 text-xs text-blue-800">
              Otevři <strong>menu sdílení</strong> v Safari (čtvereček se šipkou)
              a klikni na <strong>&bdquo;Přidat na plochu&ldquo;</strong>.
            </p>
          )}
          {deferredPrompt && (
            <button
              onClick={handleInstall}
              className="mt-2 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              Nainstalovat
            </button>
          )}
        </div>
        <button
          onClick={handleDismiss}
          className="rounded p-1 text-blue-400 hover:text-blue-600"
          aria-label="Zavřít"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
