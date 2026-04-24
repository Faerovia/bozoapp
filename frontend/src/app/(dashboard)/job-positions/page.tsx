"use client";

/**
 * Po refaktoru 13a/b se pracovní pozice spravují v modulu
 * „Provozovny, pracoviště, pozice" (/workplaces) zanořeně pod pracovištěm.
 * Tahle stránka existuje už jen kvůli uloženým záložkám — redirectuje.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function JobPositionsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/workplaces");
  }, [router]);
  return (
    <div className="p-6 text-sm text-gray-500">
      Modul byl sloučen do &quot;Provozovny, pracoviště, pozice&quot;. Přesměrovávám…
    </div>
  );
}
