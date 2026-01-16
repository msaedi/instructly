from __future__ import annotations

from types import SimpleNamespace

from app.schemas.address import ServiceAreaNeighborhoodOut
from app.schemas.search_responses import InstructorInfo


def test_instructor_info_from_user_builds_neighborhoods() -> None:
    user = SimpleNamespace(id="u1", first_name="Ada", last_name="Lovelace")
    neighborhoods = [
        {
            "id": "n1",
            "ntacode": "X1",
            "name": "Chelsea",
            "borough": "Manhattan",
        },
        ServiceAreaNeighborhoodOut(
            neighborhood_id="n2", ntacode="X2", name="SoHo", borough="Manhattan"
        ),
    ]

    info = InstructorInfo.from_user(
        user,
        bio="bio",
        years_experience=3,
        service_area_summary="Manhattan",
        service_area_boroughs=["Manhattan"],
        service_area_neighborhoods=neighborhoods,
    )

    assert info.id == "u1"
    assert info.last_initial == "L"
    assert len(info.service_area_neighborhoods) == 2


def test_instructor_info_handles_missing_last_name() -> None:
    user = SimpleNamespace(id="u2", first_name="Alan", last_name="")
    info = InstructorInfo.from_user(user)

    assert info.last_initial == ""
