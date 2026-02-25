"""Tests for app/schemas/review.py — coverage gaps L49, L52."""
from __future__ import annotations

import pytest

from app.schemas.review import ReviewSubmitRequest


@pytest.mark.unit
class TestReviewSubmitRequestCoverage:
    """Cover _clean_text validator edge cases."""

    def _valid_data(self, **overrides: object) -> dict:
        data = {
            "booking_id": "01ABC",
            "rating": 5,
        }
        data.update(overrides)
        return data

    def test_review_text_none(self) -> None:
        """L48-49: None review_text stays None."""
        req = ReviewSubmitRequest(**self._valid_data(review_text=None))
        assert req.review_text is None

    def test_review_text_valid(self) -> None:
        req = ReviewSubmitRequest(**self._valid_data(review_text="Great lesson!"))
        assert req.review_text == "Great lesson!"

    def test_review_text_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
        req = ReviewSubmitRequest(**self._valid_data(review_text="  Good job  "))
        assert req.review_text == "Good job"

    def test_review_text_whitespace_only_becomes_empty(self) -> None:
        """L49-50: whitespace-only -> strip -> empty string, which is falsy.
        v2 = ''.strip() = ''; v2 is falsy so len check is skipped; returns ''."""
        req = ReviewSubmitRequest(**self._valid_data(review_text="   "))
        # strip("   ") = "" — empty string returned
        assert req.review_text == ""

    def test_review_text_too_short_raises(self) -> None:
        """L51-52: non-empty but < 3 chars raises ValueError."""
        with pytest.raises(Exception, match="too short"):
            ReviewSubmitRequest(**self._valid_data(review_text="ab"))

    def test_review_text_single_char_raises(self) -> None:
        with pytest.raises(Exception, match="too short"):
            ReviewSubmitRequest(**self._valid_data(review_text="x"))

    def test_review_text_two_chars_raises(self) -> None:
        with pytest.raises(Exception, match="too short"):
            ReviewSubmitRequest(**self._valid_data(review_text="ok"))

    def test_review_text_exactly_three_chars_ok(self) -> None:
        req = ReviewSubmitRequest(**self._valid_data(review_text="wow"))
        assert req.review_text == "wow"

    def test_review_text_two_chars_with_whitespace_raises(self) -> None:
        """'  ab  ' -> strip -> 'ab' -> len 2 -> too short."""
        with pytest.raises(Exception, match="too short"):
            ReviewSubmitRequest(**self._valid_data(review_text="  ab  "))

    def test_rating_boundary_low(self) -> None:
        req = ReviewSubmitRequest(**self._valid_data(rating=1))
        assert req.rating == 1

    def test_rating_boundary_high(self) -> None:
        req = ReviewSubmitRequest(**self._valid_data(rating=5))
        assert req.rating == 5

    def test_rating_below_min_raises(self) -> None:
        with pytest.raises(Exception):
            ReviewSubmitRequest(**self._valid_data(rating=0))

    def test_rating_above_max_raises(self) -> None:
        with pytest.raises(Exception):
            ReviewSubmitRequest(**self._valid_data(rating=6))
