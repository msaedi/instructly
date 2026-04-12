from types import SimpleNamespace

from app.repositories.retriever._sql_helpers import _map_grouped_instructor_row


def test_map_grouped_instructor_row_includes_profile_picture_version():
    row = SimpleNamespace(
        instructor_id="inst-1",
        first_name="Ava",
        last_initial="L.",
        bio_snippet="Bio",
        years_experience=7,
        profile_picture_key="private/personal-assets/profile-pictures/inst-1/v3/original.jpg",
        profile_picture_version=3,
        verified=True,
        is_founding_instructor=False,
        matching_services=[],
        best_score=0.9,
        match_count=1,
        avg_rating=4.8,
        review_count=12,
        coverage_areas=["Lower East Side"],
    )

    result = _map_grouped_instructor_row(row)

    assert result["profile_picture_key"] == row.profile_picture_key
    assert result["profile_picture_version"] == 3
