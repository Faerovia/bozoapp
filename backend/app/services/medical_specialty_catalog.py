"""
Číselník odborných lékařských vyšetření a jejich periodicit dle kategorie práce.

Zdroj: vyhláška 79/2013 Sb. + interní příloha „Odborná vyšetření dle kategorií rizik".

Periodicita je v měsících (aby se shodla s obecným polem `valid_months`):
  - Pokud kategorie není uvedená v dictu, vyšetření není povinné.
  - Hodnota None = jen vstupní (případně nad 50 let), ne periodicky.

Klíče kategorie: "1", "2", "2R", "3", "4"
"""

from __future__ import annotations

from typing import Literal

SpecialtyKey = Literal[
    "audiometrie",
    "spirometrie",
    "prstova_plethysmografie",
    "ekg_klidove",
    "ocni_vysetreni",
    "rtg_plic",
    "psychotesty",
]


def _months(years: int) -> int:
    return years * 12


# Per-specialty mapping: kategorie → periodicita v měsících (nebo None = jen vstupní)
SPECIALTY_PERIODICITY: dict[str, dict[str, int | None]] = {
    "audiometrie": {
        "2":  _months(4),    # 4–5 let, bereme spodní hranici
        "2R": _months(2),
        "3":  _months(2),
        "4":  _months(1),
    },
    "spirometrie": {
        "2":  _months(4),
        "2R": _months(2),
        "3":  _months(2),
        "4":  _months(1),
    },
    "prstova_plethysmografie": {
        "2":  _months(4),
        "2R": _months(2),
        "3":  _months(2),
    },
    "ekg_klidove": {
        # Bez specifického období dle kategorie — typicky vstupně + nad 50 let.
        # Necháme prázdné a OZO doplní manuálně podle profese (noční práce, hasiči).
    },
    "ocni_vysetreni": {
        "2":  _months(4),
        "2R": _months(2),
        "3":  _months(2),
        "4":  _months(2),
    },
    "rtg_plic": {
        # Práce s azbestem/křemenem — typicky až po 10 letech expozice.
        # Necháme manuální plánování OZO.
        "2R": _months(3),
        "3":  _months(3),
        "4":  _months(2),
    },
    "psychotesty": {
        # Řidiči nad 7,5 t, strojvedoucí — vstupní + 50 let + 5 let.
        # Necháme manuální plánování (nezávisí přímo na kategorii).
    },
}


# Lidsky čitelné labely + popisy + cílové profese
SPECIALTY_CATALOG: list[dict[str, str]] = [
    {
        "key":   "audiometrie",
        "label": "Audiometrie",
        "purpose": "Ochrana sluchu",
        "examples": "Kovář, obsluha strojů, letištní personál",
    },
    {
        "key":   "spirometrie",
        "label": "Spirometrie",
        "purpose": "Funkce plic",
        "examples": "Svářeč, lakýrník, práce v prašném dole",
    },
    {
        "key":   "prstova_plethysmografie",
        "label": "Prstová plethysmografie",
        "purpose": "Ochrana cév rukou",
        "examples": "Lesník s pilou, dělník se sbíječkou",
    },
    {
        "key":   "ekg_klidove",
        "label": "EKG (klidové)",
        "purpose": "Srdeční rytmus",
        "examples": "Práce v noci, hasiči, velká fyzická zátěž",
    },
    {
        "key":   "ocni_vysetreni",
        "label": "Oční vyšetření",
        "purpose": "Ostrost a zorné pole",
        "examples": "Jeřábník, řidič, jemná mechanika",
    },
    {
        "key":   "rtg_plic",
        "label": "RTG plic",
        "purpose": "Změny na plicní tkáni",
        "examples": "Práce s azbestem, křemenem, v tunelu",
    },
    {
        "key":   "psychotesty",
        "label": "Psychotesty",
        "purpose": "Psychická odolnost",
        "examples": "Řidiči nad 7,5 t, strojvedoucí",
    },
]


def get_periodicity_for_category(specialty: str, category: str) -> int | None:
    """Vrátí periodicitu (měsíce) pro daný typ odborného vyšetření a kategorii práce."""
    return SPECIALTY_PERIODICITY.get(specialty, {}).get(category)


def get_required_specialties_for_category(category: str) -> list[str]:
    """Vrátí seznam doporučených odborných vyšetření pro danou kategorii práce.

    DEPRECATED — tato funkce vrací VŠECHNY odborné prohlídky bez ohledu
    na konkrétní rizikové faktory. Použít pouze jako fallback, když pozice
    nemá vyplněnou RFA. Preferuj `get_required_specialties_for_factors`.
    """
    return [
        spec for spec, mapping in SPECIALTY_PERIODICITY.items()
        if category in mapping
    ]


# ── Mapování RIZIKOVÝ FAKTOR → ODBORNÉ PROHLÍDKY ─────────────────────────────
#
# Klíčový princip nové legislativní revize: odborné prohlídky se přidělují
# JEN podle konkrétního rizikového faktoru, ne podle souhrnné kategorie pozice.
#
# Příklad: pozice má rf_hluk=4 a rf_prach=1 — přiřadí se POUZE audiometrie
# s periodicitou pro kat. 4 (1× za rok), žádná spirometrie ani RTG plic.

RISK_FACTOR_TO_SPECIALTIES: dict[str, list[str]] = {
    "rf_hluk":       ["audiometrie"],
    "rf_prach":      ["spirometrie", "rtg_plic"],
    "rf_chem":       ["spirometrie"],
    "rf_vibrace":    ["prstova_plethysmografie"],
    "rf_psych":      ["ekg_klidove"],
    "rf_fyz_zatez":  ["ekg_klidove"],
    "rf_zrak":       ["ocni_vysetreni"],
    # rf_zareni, rf_tlak, rf_prac_poloha, rf_teplo, rf_chlad, rf_bio:
    # nemají v této tabulce přímo přiřazené odborné vyšetření.
    # OZO může přidat manuálně (např. RTG při ionizujícím záření).
}


def get_required_specialties_for_factors(
    factor_ratings: dict[str, str | None],
) -> list[tuple[str, str, str]]:
    """
    Pro daný RFA matrix (faktor → rating) vrátí seznam doporučených odborných
    vyšetření spolu s odvozeným ratingem.

    Returns list of tuples: (specialty_key, source_factor, factor_rating)

    Specialty se nezduplikuje — pokud několik faktorů vede ke stejnému typu
    vyšetření, použije se ten s nejvyšším ratingem.
    """
    rating_order = ["1", "2", "2R", "3", "4"]
    # specialty → (factor, rating, rating_idx)
    best: dict[str, tuple[str, str, int]] = {}
    for factor, rating in factor_ratings.items():
        if not rating or rating == "1":
            # kategorie 1 = bez rizika, neodůvodňuje odbornou prohlídku
            continue
        idx = rating_order.index(rating) if rating in rating_order else -1
        if idx < 0:
            continue
        for spec in RISK_FACTOR_TO_SPECIALTIES.get(factor, []):
            existing = best.get(spec)
            if existing is None or existing[2] < idx:
                best[spec] = (factor, rating, idx)
    return [(spec, factor, rating) for spec, (factor, rating, _) in best.items()]
