"""Testy Risk Assessment modulu (ČSN ISO 45001).

Ověřuje:
- CRUD risk_assessments + measures
- P×Z score validace (1-5) + auto level
- Status workflow + revisions snapshot
- Scope validace (workplace/position/plant/activity)
- Archive (soft-delete)
- Permissions (role-based)
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _ozo_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ozo-ra{suffix}@firma.cz",
            "password": "heslo1234",
            "tenant_name": f"Firma RA {suffix}",
        },
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_workplace(client: AsyncClient, headers: dict) -> str:
    plant_resp = await client.post(
        "/api/v1/plants",
        json={"name": "Provozovna 1"},
        headers=headers,
    )
    plant_id = plant_resp.json()["id"]
    wp_resp = await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_id, "name": "Hala A"},
        headers=headers,
    )
    return wp_resp.json()["id"]


def _ra_payload(**overrides) -> dict:
    base = {
        "scope_type": "activity",
        "activity_description": "Práce ve výšce",
        "hazard_category": "working_at_height",
        "oopp_risk_column": 3,  # "Pády z výšky" dle NV 390/2021
        "hazard_description": "Pád z výšky při čištění oken",
        "consequence_description": "Zlomení končetin",
        "initial_probability": 3,
        "initial_severity": 4,
        "status": "open",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_risk_assessment_activity_scope(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "1")
    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["initial_score"] == 12  # 3 × 4
    assert data["initial_level"] == "high"  # 12 ∈ [10, 15]
    assert data["status"] == "open"
    assert data["scope_type"] == "activity"


@pytest.mark.asyncio
async def test_score_to_level_thresholds(client: AsyncClient) -> None:
    """1-4 low, 5-9 medium, 10-15 high, 16-25 critical."""
    headers = await _ozo_headers(client, "2")

    cases = [
        (1, 1, "low"),       # 1
        (2, 2, "low"),       # 4
        (1, 5, "medium"),    # 5
        (3, 3, "medium"),    # 9
        (2, 5, "high"),      # 10
        (3, 5, "high"),      # 15
        (4, 4, "critical"),  # 16
        (5, 5, "critical"),  # 25
    ]
    for p, s, expected_level in cases:
        resp = await client.post(
            "/api/v1/risk-assessments",
            json=_ra_payload(initial_probability=p, initial_severity=s),
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["initial_level"] == expected_level, (
            f"P={p}, S={s} → expected {expected_level}, got {resp.json()['initial_level']}"
        )


@pytest.mark.asyncio
async def test_scope_validation(client: AsyncClient) -> None:
    """workplace scope vyžaduje workplace_id, atd."""
    headers = await _ozo_headers(client, "3")

    # workplace scope bez workplace_id → 422
    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(scope_type="workplace", activity_description=None),
        headers=headers,
    )
    assert resp.status_code == 422

    # plant scope bez plant_id → 422
    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(scope_type="plant", activity_description=None),
        headers=headers,
    )
    assert resp.status_code == 422

    # activity bez activity_description → 422
    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(activity_description=None),
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_workplace_scope_with_id(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "4")
    workplace_id = await _create_workplace(client, headers)

    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(
            scope_type="workplace",
            workplace_id=workplace_id,
            activity_description=None,
        ),
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["workplace_id"] == workplace_id
    assert data["workplace_name"] == "Hala A"


@pytest.mark.asyncio
async def test_probability_severity_range(client: AsyncClient) -> None:
    """P a S musí být 1–5."""
    headers = await _ozo_headers(client, "5")
    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(initial_probability=0),
        headers=headers,
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(initial_severity=6),
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_residual_score_after_update(client: AsyncClient) -> None:
    """Update přidá residual P×S — score se přepočítá."""
    headers = await _ozo_headers(client, "6")
    create = await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(initial_probability=4, initial_severity=5),  # 20 critical
        headers=headers,
    )
    ra_id = create.json()["id"]

    # Po opatřeních residual 2×3=6 medium
    update = await client.patch(
        f"/api/v1/risk-assessments/{ra_id}",
        json={
            "residual_probability": 2,
            "residual_severity": 3,
            "status": "mitigated",
            "change_reason": "Po zavedení kolektivní ochrany",
        },
        headers=headers,
    )
    assert update.status_code == 200
    data = update.json()
    assert data["residual_score"] == 6
    assert data["residual_level"] == "medium"
    assert data["initial_score"] == 20  # zůstává


@pytest.mark.asyncio
async def test_revisions_audit_trail(client: AsyncClient) -> None:
    """Každý update vytvoří revision snapshot."""
    headers = await _ozo_headers(client, "7")
    create = await client.post(
        "/api/v1/risk-assessments", json=_ra_payload(), headers=headers,
    )
    ra_id = create.json()["id"]

    # Update 1
    await client.patch(
        f"/api/v1/risk-assessments/{ra_id}",
        json={"status": "in_progress", "change_reason": "Začínáme řešit"},
        headers=headers,
    )
    # Update 2
    await client.patch(
        f"/api/v1/risk-assessments/{ra_id}",
        json={"residual_probability": 2, "residual_severity": 2, "change_reason": "Po opatřeních"},
        headers=headers,
    )

    revisions = await client.get(
        f"/api/v1/risk-assessments/{ra_id}/revisions", headers=headers,
    )
    assert revisions.status_code == 200
    revs = revisions.json()
    # 1 vytvoření + 2 update = 3 revize
    assert len(revs) == 3
    # Pořadí DESC podle revision_number
    assert revs[0]["revision_number"] == 3
    assert revs[2]["revision_number"] == 1


@pytest.mark.asyncio
async def test_archive_via_delete(client: AsyncClient) -> None:
    """DELETE jen archivuje (status='archived'), nesmaže fyzicky."""
    headers = await _ozo_headers(client, "8")
    create = await client.post(
        "/api/v1/risk-assessments", json=_ra_payload(), headers=headers,
    )
    ra_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/risk-assessments/{ra_id}", headers=headers)
    assert delete.status_code == 204

    # Přes GET jednotlivého stále existuje (filtr status archived)
    get = await client.get(f"/api/v1/risk-assessments/{ra_id}", headers=headers)
    assert get.status_code == 200
    assert get.json()["status"] == "archived"

    # V seznamu (default bez status filtru) je vidět
    list_resp = await client.get("/api/v1/risk-assessments", headers=headers)
    ids = [r["id"] for r in list_resp.json()]
    assert ra_id in ids


@pytest.mark.asyncio
async def test_create_measure(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "9")
    create = await client.post(
        "/api/v1/risk-assessments", json=_ra_payload(), headers=headers,
    )
    ra_id = create.json()["id"]

    measure = await client.post(
        f"/api/v1/risk-assessments/{ra_id}/measures",
        json={
            "risk_assessment_id": ra_id,
            "control_type": "engineering",
            "description": "Instalace zábradlí",
            "status": "planned",
        },
        headers=headers,
    )
    assert measure.status_code == 201
    assert measure.json()["control_type"] == "engineering"

    measures = await client.get(
        f"/api/v1/risk-assessments/{ra_id}/measures", headers=headers,
    )
    assert len(measures.json()) == 1


_ACCIDENT_PAYLOAD = {
    "employee_name": "Jan Novák",
    "workplace": "Hala A – sklad",
    "accident_date": "2026-03-15",
    "accident_time": "10:30:00",
    "shift_start_time": "06:00:00",
    "injury_type": "Zlomenina",
    "injured_body_part": "Levé předloktí",
    "injured_body_part_code": "H",  # paže (části)
    "injury_source": "Padající předmět",
    "injury_cause": "Špatně zajištěný materiál na regálu",
    "injured_count": 1,
    "is_fatal": False,
    "has_other_injuries": False,
    "description": "Zaměstnanec procházel mezi regály, spadl karton.",
    "blood_pathogen_exposure": False,
    "alcohol_test_performed": True,
    "alcohol_test_result": "negative",
    "drug_test_performed": False,
    "witnesses": [{"name": "Marie Svobodová"}],
    "supervisor_name": "Petr Kovář",
}


@pytest.mark.asyncio
async def test_accident_create_auto_links_risk_assessment(client: AsyncClient) -> None:
    """Vytvoření úrazu (i v draft fázi) musí automaticky:
    1) vytvořit AccidentActionItem 'Revize a případná změna rizik' (is_default)
    2) vytvořit/najít placeholder RiskAssessment
    3) napojit action item přes related_risk_assessment_id na to RA.
    """
    headers = await _ozo_headers(client, "11")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_ACCIDENT_PAYLOAD, headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    accident = create_resp.json()
    accident_id = accident["id"]
    # Úraz je v draft stavu — žádný finalize
    assert accident["status"] == "draft"

    # Action plán už obsahuje default položku (vznikla při create)
    items_resp = await client.get(
        f"/api/v1/accident-reports/{accident_id}/action-items", headers=headers,
    )
    assert items_resp.status_code == 200
    items = items_resp.json()
    default_items = [i for i in items if i.get("is_default")]
    assert len(default_items) == 1
    default_item = default_items[0]
    assert default_item["status"] == "pending"
    # Item musí být napojen na placeholder RA
    assert default_item["related_risk_assessment_id"] is not None


@pytest.mark.asyncio
async def test_closing_ra_closes_linked_accident_action_item(
    client: AsyncClient,
) -> None:
    """Když OZO uzavře RA (status='accepted'), navázaný action item v úrazu
    se musí automaticky uzavřít (status='done', completed_at se nastaví)."""
    headers = await _ozo_headers(client, "12")
    create_resp = await client.post(
        "/api/v1/accident-reports", json=_ACCIDENT_PAYLOAD, headers=headers,
    )
    accident_id = create_resp.json()["id"]

    items_resp = await client.get(
        f"/api/v1/accident-reports/{accident_id}/action-items", headers=headers,
    )
    default_item = next(i for i in items_resp.json() if i.get("is_default"))
    ra_id = default_item["related_risk_assessment_id"]
    assert ra_id is not None
    item_id = default_item["id"]

    # Uzavři RA — sémanticky 'accepted' = riziko posouzeno a uzavřeno
    close_resp = await client.patch(
        f"/api/v1/risk-assessments/{ra_id}",
        json={"status": "accepted", "change_reason": "Po analýze nebyly nutné další změny."},
        headers=headers,
    )
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["status"] == "accepted"

    # Action item v úrazu je teď done
    items_after = await client.get(
        f"/api/v1/accident-reports/{accident_id}/action-items", headers=headers,
    )
    closed_item = next(i for i in items_after.json() if i["id"] == item_id)
    assert closed_item["status"] == "done"
    assert closed_item["completed_at"] is not None


@pytest.mark.asyncio
async def test_filter_by_status_and_level(client: AsyncClient) -> None:
    headers = await _ozo_headers(client, "10")

    # Critical riziko
    await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(initial_probability=5, initial_severity=5, status="open"),
        headers=headers,
    )
    # Low riziko
    await client.post(
        "/api/v1/risk-assessments",
        json=_ra_payload(initial_probability=1, initial_severity=2, status="mitigated"),
        headers=headers,
    )

    # Filter status=open
    open_list = await client.get(
        "/api/v1/risk-assessments?ra_status=open", headers=headers,
    )
    assert len(open_list.json()) == 1

    # Filter level=critical
    critical = await client.get(
        "/api/v1/risk-assessments?level=critical", headers=headers,
    )
    assert len(critical.json()) == 1
    assert critical.json()[0]["initial_score"] == 25


@pytest.mark.asyncio
async def test_ppe_measure_auto_toggles_oopp_grid(client: AsyncClient) -> None:
    """End-to-end flow: úraz → RA → PPE measure → auto-zaškrtnutí v OOPP gridu.

    1) Vytvořit pracoviště + pozici + zaměstnance
    2) Vytvořit úraz s injured_body_part_code='H' (paže)
    3) Default action item odkazuje na placeholder RA
    4) Aktualizovat RA s oopp_risk_column=3 (Pády z výšky)
    5) Přidat measure control_type='ppe'
    6) Zkontrolovat OOPP grid pozice — měl by obsahovat (H, 3)
    """
    headers = await _ozo_headers(client, "13")

    # 1) Pracoviště + pozice
    plant_resp = await client.post(
        "/api/v1/plants", json={"name": "Provozovna 1"}, headers=headers,
    )
    plant_id = plant_resp.json()["id"]
    wp_resp = await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_id, "name": "Hala A"},
        headers=headers,
    )
    wp_id = wp_resp.json()["id"]
    pos_resp = await client.post(
        "/api/v1/job-positions",
        json={"workplace_id": wp_id, "name": "Skladník"},
        headers=headers,
    )
    pos_id = pos_resp.json()["id"]

    # 2) Zaměstnanec na pozici
    emp_resp = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Jan",
            "last_name": "Novák",
            "personal_id": "9001011234",
            "personal_number": "EMP001",
            "employment_type": "hpp",
            "job_position_id": pos_id,
            "workplace_id": wp_id,
        },
        headers=headers,
    )
    assert emp_resp.status_code in (200, 201), emp_resp.text
    emp_id = emp_resp.json()["id"]

    # 3) Úraz s body_part_code='H'
    accident_payload = {
        **_ACCIDENT_PAYLOAD,
        "employee_id": emp_id,
        "workplace_id": wp_id,
        "injured_body_part_code": "H",
    }
    accident_resp = await client.post(
        "/api/v1/accident-reports", json=accident_payload, headers=headers,
    )
    assert accident_resp.status_code == 201, accident_resp.text
    accident_id = accident_resp.json()["id"]

    # Zjisti RA z action plánu
    items_resp = await client.get(
        f"/api/v1/accident-reports/{accident_id}/action-items", headers=headers,
    )
    default_item = next(i for i in items_resp.json() if i.get("is_default"))
    ra_id = default_item["related_risk_assessment_id"]
    assert ra_id is not None

    # 4) OZO doplní RA — nastaví oopp_risk_column=3 (Pády z výšky)
    patch_resp = await client.patch(
        f"/api/v1/risk-assessments/{ra_id}",
        json={"oopp_risk_column": 3, "change_reason": "OZO doplnil sloupec OOPP"},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text

    # 5) Přidat PPE measure
    measure_resp = await client.post(
        f"/api/v1/risk-assessments/{ra_id}/measures",
        json={
            "risk_assessment_id": ra_id,
            "control_type": "ppe",
            "description": "Helma + úvazek",
            "status": "planned",
        },
        headers=headers,
    )
    assert measure_resp.status_code == 201, measure_resp.text

    # 6) OOPP grid pro pozici musí obsahovat (H, 3)
    grid_resp = await client.get(
        f"/api/v1/job-positions/{pos_id}/oopp-grid", headers=headers,
    )
    assert grid_resp.status_code == 200, grid_resp.text
    grid = grid_resp.json().get("grid", {})
    assert "H" in grid, f"Body part 'H' nenalezena v gridu: {grid}"
    assert 3 in grid["H"], f"Risk col 3 nenalezen v grid['H']: {grid['H']}"


@pytest.mark.asyncio
async def test_ppe_measure_grid_idempotent(client: AsyncClient) -> None:
    """Druhé volání create_measure pro stejný (body_part, risk_col) nesmí
    duplikovat políčko v gridu."""
    headers = await _ozo_headers(client, "14")

    # Setup pracoviště/pozice/zaměstnanec — zkrácená varianta předchozího testu
    plant_id = (await client.post(
        "/api/v1/plants", json={"name": "P14"}, headers=headers,
    )).json()["id"]
    wp_id = (await client.post(
        "/api/v1/workplaces",
        json={"plant_id": plant_id, "name": "WP14"}, headers=headers,
    )).json()["id"]
    pos_id = (await client.post(
        "/api/v1/job-positions",
        json={"workplace_id": wp_id, "name": "Pos14"}, headers=headers,
    )).json()["id"]
    emp_id = (await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Test", "last_name": "T14",
            "personal_id": "9001011234", "personal_number": "T14",
            "employment_type": "hpp",
            "job_position_id": pos_id, "workplace_id": wp_id,
        },
        headers=headers,
    )).json()["id"]

    accident_id = (await client.post(
        "/api/v1/accident-reports",
        json={**_ACCIDENT_PAYLOAD, "employee_id": emp_id, "workplace_id": wp_id,
              "injured_body_part_code": "G"},
        headers=headers,
    )).json()["id"]
    items = (await client.get(
        f"/api/v1/accident-reports/{accident_id}/action-items", headers=headers,
    )).json()
    ra_id = next(i for i in items if i.get("is_default"))["related_risk_assessment_id"]

    await client.patch(
        f"/api/v1/risk-assessments/{ra_id}",
        json={"oopp_risk_column": 6, "change_reason": "doplnit"},
        headers=headers,
    )

    # 2× PPE measure
    for _ in range(2):
        await client.post(
            f"/api/v1/risk-assessments/{ra_id}/measures",
            json={
                "risk_assessment_id": ra_id,
                "control_type": "ppe",
                "description": "Rukavice",
                "status": "planned",
            },
            headers=headers,
        )

    grid = (await client.get(
        f"/api/v1/job-positions/{pos_id}/oopp-grid", headers=headers,
    )).json().get("grid", {})
    # Bez duplicit: G obsahuje 6 právě jednou
    assert grid.get("G", []).count(6) == 1
