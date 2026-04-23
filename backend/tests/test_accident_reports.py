"""
Testy pro záznamy o pracovních úrazech.

BOZP invarianty:
- draft → final workflow, final je immutable
- finalizace nastaví risk_review_required = True
- complete-risk-review nastaví risk_review_completed_at
- archivace místo smazání
- employee nemůže vytvářet záznamy
- PDF endpoint vrátí správný Content-Type a Content-Disposition
"""

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo{suffix}@uraz.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _employee_headers(client: AsyncClient, ozo_headers: dict, suffix: str) -> dict:
    await client.post(
        "/api/v1/users",
        json={"email": f"emp{suffix}@uraz.cz", "password": "heslo1234", "role": "employee"},
        headers=ozo_headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"emp{suffix}@uraz.cz", "password": "heslo1234"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _report_payload(**overrides) -> dict:
    base = {
        "employee_name": "Jan Novák",
        "workplace": "Hala A – sklad",
        "accident_date": "2026-03-15",
        "accident_time": "10:30:00",
        "shift_start_time": "06:00:00",
        "injury_type": "Zlomenina",
        "injured_body_part": "Levé předloktí",
        "injury_source": "Padající předmět",
        "injury_cause": "Špatně zajištěný materiál na regálu",
        "injured_count": 1,
        "is_fatal": False,
        "has_other_injuries": False,
        "description": "Zaměstnanec procházel mezi regály, na něj spadl karton s materiálem.",
        "blood_pathogen_exposure": False,
        "alcohol_test_performed": True,
        "alcohol_test_result": "negative",
        "drug_test_performed": False,
        "witnesses": [{"name": "Marie Svobodová"}],
        "supervisor_name": "Petr Kovář",
    }
    base.update(overrides)
    return base


# ── Vytvoření draftu ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_draft_report(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar1")
    resp = await client.post("/api/v1/accident-reports", json=_report_payload(), headers=headers)

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["risk_review_required"] is False
    assert data["employee_name"] == "Jan Novák"


@pytest.mark.asyncio
async def test_edit_draft_report(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar2")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/accident-reports/{report_id}",
        json={"workplace": "Hala B – výroba"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["workplace"] == "Hala B – výroba"


# ── Workflow: finalizace ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finalize_sets_risk_review_required(client: AsyncClient) -> None:
    """
    Kritický invariant: po finalizaci musí OZO provést revizi rizik.
    """
    headers = await _ozo_headers(client, "ar3")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]

    final_resp = await client.post(
        f"/api/v1/accident-reports/{report_id}/finalize", headers=headers
    )
    assert final_resp.status_code == 200
    data = final_resp.json()
    assert data["status"] == "final"
    assert data["risk_review_required"] is True
    assert data["risk_review_completed_at"] is None


@pytest.mark.asyncio
async def test_cannot_edit_final_report(client: AsyncClient) -> None:
    """
    Kritický invariant: finalizovaný záznam je immutable.
    """
    headers = await _ozo_headers(client, "ar4")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]
    await client.post(f"/api/v1/accident-reports/{report_id}/finalize", headers=headers)

    patch_resp = await client.patch(
        f"/api/v1/accident-reports/{report_id}",
        json={"workplace": "Pokus o změnu"},
        headers=headers,
    )
    assert patch_resp.status_code == 422


@pytest.mark.asyncio
async def test_cannot_finalize_already_final(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar5")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]
    await client.post(f"/api/v1/accident-reports/{report_id}/finalize", headers=headers)

    second_finalize = await client.post(
        f"/api/v1/accident-reports/{report_id}/finalize", headers=headers
    )
    assert second_finalize.status_code == 422


# ── Workflow: revize rizik ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_risk_review(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar6")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]
    await client.post(f"/api/v1/accident-reports/{report_id}/finalize", headers=headers)

    review_resp = await client.post(
        f"/api/v1/accident-reports/{report_id}/complete-risk-review", headers=headers
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["risk_review_completed_at"] is not None


# ── Archivace ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_report_keeps_record(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar7")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/accident-reports/{report_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/accident-reports/{report_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "archived"


# ── Permissions ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_cannot_create_report(client: AsyncClient) -> None:
    ozo_headers = await _ozo_headers(client, "ar8")
    emp_headers = await _employee_headers(client, ozo_headers, "8")

    resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=emp_headers
    )
    assert resp.status_code == 403


# ── PDF export ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pdf_inline_content_disposition(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar9")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]

    pdf_resp = await client.get(
        f"/api/v1/accident-reports/{report_id}/pdf", headers=headers
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.headers["content-disposition"].startswith("inline")
    assert len(pdf_resp.content) > 1000  # smysluplný PDF obsah


@pytest.mark.asyncio
async def test_pdf_download_content_disposition(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "ar10")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_report_payload(), headers=headers
    )
    report_id = create_resp.json()["id"]

    pdf_resp = await client.get(
        f"/api/v1/accident-reports/{report_id}/pdf?download=true", headers=headers
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-disposition"].startswith("attachment")
