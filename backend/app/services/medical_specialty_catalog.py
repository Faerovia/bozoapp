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
    """Vrátí seznam doporučených odborných vyšetření pro danou kategorii práce."""
    return [
        spec for spec, mapping in SPECIALTY_PERIODICITY.items()
        if category in mapping
    ]
