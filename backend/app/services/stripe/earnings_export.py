from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
import io
import logging
from typing import TYPE_CHECKING, Any, Optional

from ...constants.payment_status import map_payment_status
from ...constants.pricing_defaults import PRICING_DEFAULTS
from ...core.exceptions import ServiceException
from ..base import BaseService
from ..config_service import ConfigService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ...repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


class StripeEarningsExportMixin(BaseService):
    """Instructor earnings CSV/PDF export helpers."""

    db: Session
    config_service: ConfigService
    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository

    def _compute_export_base_price_cents(self, hourly_rate: Any, duration_minutes: int) -> int:
        try:
            rate = Decimal(str(hourly_rate or 0))
            cents_value = rate * Decimal(duration_minutes) * Decimal(100) / Decimal(60)
            return int(cents_value.quantize(Decimal("1")))
        except Exception:
            # Export generation should continue even when individual rows contain malformed pricing.
            return 0

    def _get_export_instructor_tier_pct(
        self, config: dict[str, Any], instructor_profile: Any
    ) -> float:
        is_founding = getattr(instructor_profile, "is_founding_instructor", False)
        if is_founding is True:
            default_rate = PRICING_DEFAULTS.get("founding_instructor_rate_pct", 0)
            raw_rate = config.get("founding_instructor_rate_pct", default_rate)
            try:
                return float(Decimal(str(raw_rate)))
            except Exception:
                return float(default_rate)

        tiers = config.get("instructor_tiers") or PRICING_DEFAULTS.get("instructor_tiers", [])
        if tiers:
            entry_tier = min(tiers, key=lambda tier: tier.get("min", 0))
            default_entry_pct = PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0)
            default_pct = float(entry_tier.get("pct", default_entry_pct))
        else:
            default_pct = float(PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0))

        raw_pct = getattr(instructor_profile, "current_tier_pct", None)
        if raw_pct is None:
            return default_pct
        try:
            pct_decimal = Decimal(str(raw_pct))
            if pct_decimal > 1:
                pct_decimal = pct_decimal / Decimal("100")
            return float(pct_decimal)
        except Exception:
            return default_pct

    def _load_earnings_export_context(self, instructor_id: str) -> dict[str, Any]:
        profile = self.instructor_repository.get_by_user_id(instructor_id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        pricing_config, _ = self.config_service.get_pricing_config()
        return {
            "pricing_config": pricing_config,
            "fallback_tier_pct": self._get_export_instructor_tier_pct(pricing_config, profile),
        }

    def _format_earnings_export_row(
        self, *, row: dict[str, Any], fallback_tier_pct: float
    ) -> dict[str, Any]:
        lesson_price_cents = self._compute_export_base_price_cents(
            row.get("hourly_rate"),
            int(row.get("duration_minutes") or 0),
        )
        net_earnings_cents = max(
            0,
            int(row.get("payment_amount_cents") or 0) - int(row.get("application_fee_cents") or 0),
        )
        actual_instructor_fee_cents = lesson_price_cents - net_earnings_cents
        if lesson_price_cents > 0 and actual_instructor_fee_cents >= 0:
            actual_tier_pct = float(actual_instructor_fee_cents) / float(lesson_price_cents)
            if not (0 <= actual_tier_pct <= 0.25):
                actual_tier_pct = fallback_tier_pct
        else:
            actual_tier_pct = fallback_tier_pct

        platform_fee_cents = actual_instructor_fee_cents if actual_instructor_fee_cents >= 0 else 0
        status_label = map_payment_status(row.get("status")).replace("_", " ").title()
        return {
            "lesson_date": row.get("lesson_date"),
            "student_name": row.get("student_name") or "Student",
            "service_name": row.get("service_name") or "Lesson",
            "duration_minutes": row.get("duration_minutes") or 0,
            "lesson_price_cents": lesson_price_cents,
            "platform_fee_cents": platform_fee_cents,
            "net_earnings_cents": net_earnings_cents,
            "status": status_label,
            "payment_id": row.get("payment_id") or "",
        }

    def _build_earnings_export_rows(
        self,
        *,
        instructor_id: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> list[dict[str, Any]]:
        context = self._load_earnings_export_context(instructor_id)
        earnings_rows = self.payment_repository.get_instructor_earnings_for_export(
            instructor_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            self._format_earnings_export_row(
                row=row,
                fallback_tier_pct=context["fallback_tier_pct"],
            )
            for row in earnings_rows
        ]

    @BaseService.measure_operation("stripe_generate_earnings_csv")
    def generate_earnings_csv(
        self,
        *,
        instructor_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> str:
        """Generate CSV export for instructor earnings."""
        rows = self._build_earnings_export_rows(
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "Date",
                "Student",
                "Service",
                "Duration (min)",
                "Lesson Price",
                "Platform Fee",
                "Net Earnings",
                "Status",
                "Payment ID",
            ]
        )
        for row in rows:
            lesson_date = row.get("lesson_date")
            writer.writerow(
                [
                    lesson_date.isoformat() if lesson_date else "",
                    row.get("student_name"),
                    row.get("service_name"),
                    row.get("duration_minutes"),
                    f"${row.get('lesson_price_cents', 0) / 100:.2f}",
                    f"${row.get('platform_fee_cents', 0) / 100:.2f}",
                    f"${row.get('net_earnings_cents', 0) / 100:.2f}",
                    row.get("status"),
                    row.get("payment_id"),
                ]
            )
        return output.getvalue()

    def _earnings_pdf_columns(self) -> list[dict[str, Any]]:
        return [
            {"label": "Date", "width": 10, "align": "left"},
            {"label": "Student", "width": 14, "align": "left"},
            {"label": "Service", "width": 20, "align": "left"},
            {"label": "Dur", "width": 5, "align": "right"},
            {"label": "Lesson", "width": 10, "align": "right"},
            {"label": "Fee", "width": 10, "align": "right"},
            {"label": "Net", "width": 10, "align": "right"},
            {"label": "Status", "width": 10, "align": "left"},
            {"label": "Payment", "width": 10, "align": "left"},
        ]

    def _fit_pdf_cell(self, text: str, width: int, align: str) -> str:
        if len(text) > width:
            text = text[:width] if width <= 3 else f"{text[: width - 3]}..."
        return text.rjust(width) if align == "right" else text.ljust(width)

    def _format_pdf_row(self, values: list[str], columns: list[dict[str, Any]]) -> str:
        return " ".join(
            self._fit_pdf_cell(value, column["width"], column["align"])
            for value, column in zip(values, columns)
        )

    def _build_earnings_pdf_header_lines(
        self,
        *,
        columns: list[dict[str, Any]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> list[str]:
        header_row = self._format_pdf_row([column["label"] for column in columns], columns)
        return [
            "Earnings Report",
            f"Range: {start_date.isoformat() if start_date else 'N/A'} to "
            f"{end_date.isoformat() if end_date else 'N/A'}",
            "",
            header_row,
            "-" * len(header_row),
        ]

    def _build_earnings_pdf_body_lines(
        self, rows: list[dict[str, Any]], columns: list[dict[str, Any]]
    ) -> list[str]:
        if not rows:
            return ["No earnings found for the selected range."]

        body_lines: list[str] = []
        for row in rows:
            lesson_date = row.get("lesson_date")
            body_lines.append(
                self._format_pdf_row(
                    [
                        lesson_date.isoformat() if lesson_date else "",
                        str(row.get("student_name") or ""),
                        str(row.get("service_name") or ""),
                        str(row.get("duration_minutes") or 0),
                        f"${row.get('lesson_price_cents', 0) / 100:.2f}",
                        f"${row.get('platform_fee_cents', 0) / 100:.2f}",
                        f"${row.get('net_earnings_cents', 0) / 100:.2f}",
                        str(row.get("status") or ""),
                        str(row.get("payment_id") or ""),
                    ],
                    columns,
                )
            )
        return body_lines

    def _escape_pdf_text(self, value: str) -> str:
        sanitized = value.encode("ascii", "replace").decode("ascii")
        return (
            sanitized.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", "")
            .replace("\n", " ")
        )

    def _render_pdf_document(self, *, header: list[str], data_lines: list[str]) -> bytes:
        page_width = 612
        page_height = 792
        left_margin = 40
        top_margin = 742
        line_height = 12
        font_size = 9
        usable_height = top_margin - 72
        lines_per_page = max(1, int(usable_height / line_height))
        data_per_page = max(1, lines_per_page - len(header))
        if not data_lines:
            pages = [header + [""]]
        else:
            pages = [
                header + data_lines[idx : idx + data_per_page]
                for idx in range(0, len(data_lines), data_per_page)
            ]

        page_obj_nums = [4 + index * 2 for index in range(len(pages))]
        content_obj_nums = [5 + index * 2 for index in range(len(pages))]
        kids = " ".join(f"{num} 0 R" for num in page_obj_nums)
        objects: list[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        ]

        for page_index, page_lines in enumerate(pages):
            content_obj_num = content_obj_nums[page_index]
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_num} 0 R >>"
            ).encode("ascii")
            objects.append(page_obj)
            content_lines = ["BT", f"/F1 {font_size} Tf", f"{left_margin} {top_margin} Td"]
            for line_index, line in enumerate(page_lines):
                if line_index > 0:
                    content_lines.append(f"0 -{line_height} Td")
                content_lines.append(f"({self._escape_pdf_text(line)}) Tj")
            content_lines.append("ET")
            content_stream = "\n".join(content_lines).encode("ascii")
            objects.append(
                f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
                + content_stream
                + b"\nendstream"
            )

        buffer = io.BytesIO()
        buffer.write(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(buffer.tell())
            buffer.write(f"{index} 0 obj\n".encode("ascii"))
            buffer.write(obj)
            buffer.write(b"\nendobj\n")
        xref_offset = buffer.tell()
        buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        buffer.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        buffer.write(b"trailer\n")
        buffer.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii"))
        buffer.write(b"startxref\n")
        buffer.write(f"{xref_offset}\n".encode("ascii"))
        buffer.write(b"%%EOF")
        return buffer.getvalue()

    @BaseService.measure_operation("stripe_generate_earnings_pdf")
    def generate_earnings_pdf(
        self,
        *,
        instructor_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> bytes:
        """Generate PDF export for instructor earnings."""
        rows = self._build_earnings_export_rows(
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )
        columns = self._earnings_pdf_columns()
        header_lines = self._build_earnings_pdf_header_lines(
            columns=columns,
            start_date=start_date,
            end_date=end_date,
        )
        body_lines = self._build_earnings_pdf_body_lines(rows, columns)
        return self._render_pdf_document(header=header_lines, data_lines=body_lines)
