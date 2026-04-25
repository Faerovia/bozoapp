"""
HTTP utility helpery — bezpečné headery, encoding, …

content_disposition() generuje Content-Disposition header s ASCII fallbackem
+ RFC 5987 `filename*=UTF-8''...` pro správné zobrazení diakritiky v moderních
prohlížečích. Bez tohoto helperu české znaky (ř, ě, ú, …) v názvu souboru
selžou v latin-1 encodingu, který Starlette/uvicorn vyžadují pro HTTP headery.
"""
from __future__ import annotations

import unicodedata
from urllib.parse import quote


def _ascii_fallback(filename: str) -> str:
    """Odstraní diakritiku, nepovolené znaky nahradí podtržítkem."""
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_only = normalized.encode("ascii", errors="ignore").decode("ascii")
    # V quoted-string nesmí být " ani \. Ostatní ASCII je OK.
    cleaned = ascii_only.replace('"', "").replace("\\", "")
    return cleaned or "download"


def content_disposition(filename: str, *, inline: bool = True) -> str:
    """
    Sestaví hodnotu Content-Disposition headeru s podporou Unicode v názvu.

    Příklad:
        >>> content_disposition("kniha_úrazů_2026.pdf", inline=False)
        'attachment; filename="kniha_urazu_2026.pdf"; filename*=UTF-8\\'\\'kniha_%C3%BArazu...'

    Použití v FastAPI Response:
        return Response(content=..., headers={
            "Content-Disposition": content_disposition(filename, inline=False),
        })
    """
    disposition = "inline" if inline else "attachment"
    ascii_name = _ascii_fallback(filename)
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"
