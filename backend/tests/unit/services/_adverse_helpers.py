"""Helpers for adverse-action unit tests."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.instructor import BGCAdverseActionEvent


def ensure_adverse_schema(db: Session) -> None:
    """Ensure new adverse-action columns and tables exist for tests."""

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text(
                "ALTER TABLE instructor_profiles "
                "ADD COLUMN IF NOT EXISTS bgc_pre_adverse_notice_id VARCHAR(26)"
            )
        )
        db.execute(
            text(
                "ALTER TABLE instructor_profiles "
                "ADD COLUMN IF NOT EXISTS bgc_pre_adverse_sent_at TIMESTAMP WITH TIME ZONE"
            )
        )
        db.execute(
            text(
                "ALTER TABLE instructor_profiles "
                "ADD COLUMN IF NOT EXISTS bgc_final_adverse_sent_at TIMESTAMP WITH TIME ZONE"
            )
        )
        db.commit()

    BGCAdverseActionEvent.__table__.create(bind, checkfirst=True)
