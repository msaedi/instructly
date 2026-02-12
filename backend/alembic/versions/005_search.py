# backend/alembic/versions/005_search.py
"""Search schema - history, analytics, regions, and NL search

Revision ID: 005_search
Revises: 004_messaging
Create Date: 2025-02-10 00:00:04.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005_search"
down_revision: Union[str, None] = "004_messaging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create search and location schema."""
    print("Creating search schema...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"
    json_type = sa.dialects.postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    # Search history
    op.create_table(
        "search_history",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=True),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.String(), nullable=False),
        sa.Column(
            "search_type",
            sa.String(20),
            nullable=False,
            server_default="natural_language",
        ),
        sa.Column("results_count", sa.Integer(), nullable=True),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.Column(
            "last_searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guest_session_id", sa.String(36), nullable=True),
        sa.Column("converted_to_user_id", sa.String(26), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["converted_to_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Tracks deduplicated user search history for clean UX",
    )

    op.create_table(
        "search_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=True),
        sa.Column("guest_session_id", sa.String(36), nullable=True),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column(
            "search_type",
            sa.String(20),
            nullable=False,
            server_default="natural_language",
        ),
        sa.Column("results_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column(
            "searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("referrer", sa.String(255), nullable=True),
        sa.Column("search_context", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("ip_address_hash", sa.String(64), nullable=True),
        sa.Column("geo_data", sa.JSON(), nullable=True),
        sa.Column("device_type", sa.String(20), nullable=True),
        sa.Column("browser_info", sa.JSON(), nullable=True),
        sa.Column("connection_type", sa.String(20), nullable=True),
        sa.Column("page_view_count", sa.Integer(), nullable=True),
        sa.Column("session_duration", sa.Integer(), nullable=True),
        sa.Column("is_returning_user", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("consent_given", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("consent_type", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Append-only event log for search analytics",
    )

    op.create_table(
        "search_interactions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("search_event_id", sa.String(26), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("interaction_type", sa.String(50), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=True),
        sa.Column("result_position", sa.Integer(), nullable=True),
        sa.Column("time_to_interaction", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["search_event_id"],
            ["search_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Tracks user interactions with search results",
    )

    op.create_index(
        "idx_search_history_user_last_searched",
        "search_history",
        ["user_id", "last_searched_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"last_searched_at": "DESC"},
    )
    op.create_index("idx_search_history_deleted", "search_history", ["deleted_at"], unique=False)
    op.create_index("idx_search_history_guest_session", "search_history", ["guest_session_id"], unique=False)
    op.create_index(
        "idx_search_history_conversion",
        "search_history",
        ["converted_to_user_id", "converted_at"],
        unique=False,
    )
    op.create_index(
        "idx_search_history_normalized_query",
        "search_history",
        ["normalized_query"],
        unique=False,
    )
    op.create_index(
        "uq_search_history_user_normalized_query",
        "search_history",
        ["user_id", "normalized_query"],
        unique=True,
    )
    op.create_index(
        "uq_search_history_guest_normalized_query",
        "search_history",
        ["guest_session_id", "normalized_query"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_search_history_type",
        "search_history",
        "search_type IN ('natural_language', 'category', 'service_pill', 'filter', 'search_history')",
    )
    op.create_check_constraint(
        "ck_search_history_user_or_guest",
        "search_history",
        "(user_id IS NOT NULL) OR (guest_session_id IS NOT NULL)",
    )

    op.create_index("idx_search_events_user_id", "search_events", ["user_id"], unique=False)
    op.create_index("idx_search_events_guest_session", "search_events", ["guest_session_id"], unique=False)
    op.create_index(
        "idx_search_events_searched_at",
        "search_events",
        ["searched_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"searched_at": "DESC"},
    )
    op.create_index("idx_search_events_query", "search_events", ["search_query"], unique=False)
    op.create_index("idx_search_events_session_id", "search_events", ["session_id"], unique=False)
    op.create_check_constraint(
        "ck_search_events_search_type",
        "search_events",
        "search_type IN ("
        "'natural_language', 'category', 'service_pill', 'filter', 'search_history',"
        "'location', 'browse'"
        ")",
    )
    op.create_check_constraint(
        "ck_search_interactions_type",
        "search_interactions",
        "interaction_type IN ('view', 'click', 'hover', 'bookmark', 'view_profile', 'contact', 'book')",
    )

    op.create_index("idx_search_interactions_event_id", "search_interactions", ["search_event_id"])
    op.create_index("idx_search_interactions_type", "search_interactions", ["interaction_type"])
    op.create_index("idx_search_interactions_instructor", "search_interactions", ["instructor_id"])
    op.create_index("idx_search_events_geo_country", "search_events", [sa.text("(geo_data->>'country_code')")])
    op.create_index("idx_search_events_geo_borough", "search_events", [sa.text("(geo_data->>'borough')")])
    op.create_index("idx_search_events_geo_postal", "search_events", [sa.text("(geo_data->>'postal_code')")])
    op.create_index("idx_search_events_device_type", "search_events", ["device_type"])
    op.create_index(
        "idx_search_events_created_at",
        "search_events",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index("idx_search_events_user_date", "search_events", ["user_id", "created_at"])

    # Service analytics
    op.create_table(
        "service_analytics",
        sa.Column("service_catalog_id", sa.String(26), nullable=False),
        sa.Column("search_count_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_count_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booking_count_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booking_count_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_to_view_rate", sa.Float(), nullable=True),
        sa.Column("view_to_booking_rate", sa.Float(), nullable=True),
        sa.Column("avg_price_booked_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_percentile_25_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_percentile_50_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_percentile_75_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("most_booked_duration", sa.Integer(), nullable=True),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("active_instructors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_weekly_hours", sa.Float(), nullable=True),
        sa.Column("supply_demand_ratio", sa.Float(), nullable=True),
        sa.Column(
            "last_calculated",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_catalog_id"],
            ["service_catalog.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("service_catalog_id"),
        comment="Analytics and intelligence data for each service in the catalog",
    )

    op.create_index("idx_service_analytics_search_count_7d", "service_analytics", ["search_count_7d"])
    op.create_index("idx_service_analytics_booking_count_30d", "service_analytics", ["booking_count_30d"])
    op.create_index("idx_service_analytics_last_calculated", "service_analytics", ["last_calculated"])

    # Observability for search
    op.create_table(
        "search_event_candidates",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("search_event_id", sa.String(26), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False, comment="1-based rank in candidate list"),
        sa.Column("service_catalog_id", sa.String(26), nullable=True),
        sa.Column("score", sa.Float(), nullable=True, comment="primary score used for ordering (e.g., hybrid)"),
        sa.Column("vector_score", sa.Float(), nullable=True, comment="raw vector similarity if available"),
        sa.Column("lexical_score", sa.Float(), nullable=True, comment="text/trigram or token overlap score if available"),
        sa.Column("source", sa.String(20), nullable=True, comment="vector|trgm|exact|hybrid"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["search_event_id"], ["search_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_catalog_id"], ["service_catalog.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="Top-N candidates considered for a search event (observability)",
    )
    op.create_index(
        "idx_search_event_candidates_event_position",
        "search_event_candidates",
        ["search_event_id", "position"],
        unique=True,
    )
    op.create_index(
        "idx_search_event_candidates_service_created",
        "search_event_candidates",
        ["service_catalog_id", "created_at"],
        unique=False,
    )

    # Lightweight Geometry type for migrations without geoalchemy2 dependency
    class Geometry(sa.types.UserDefinedType):
        def __init__(self, geom_type: str = "POINT", srid: int = 4326):
            self.geom_type = geom_type
            self.srid = srid

        def get_col_spec(self, **kw):  # type: ignore[override]
            return f"GEOMETRY({self.geom_type}, {self.srid})"

    print("Creating region_boundaries table...")
    op.create_table(
        "region_boundaries",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("region_type", sa.String(50), nullable=False),
        sa.Column("region_code", sa.String(50), nullable=True),
        sa.Column("region_name", sa.String(100), nullable=True),
        sa.Column("parent_region", sa.String(100), nullable=True),
        sa.Column("boundary", Geometry("MULTIPOLYGON", 4326), nullable=True),
        sa.Column("centroid", Geometry("POINT", 4326), nullable=True),
        sa.Column("region_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    if is_postgres:
        op.create_index(
            "ix_region_boundaries_boundary",
            "region_boundaries",
            ["boundary"],
            postgresql_using="gist",
        )
    op.create_index("ix_region_boundaries_type", "region_boundaries", ["region_type"])
    op.create_index("ix_region_boundaries_region", "region_boundaries", ["region_type", "region_code"])
    op.create_index("ix_region_boundaries_name", "region_boundaries", ["region_type", "region_name"])
    op.create_index(
        "region_boundaries_rtype_rcode_idx",
        "region_boundaries",
        ["region_type", "region_code"],
        unique=True,
    )

    print("Creating instructor_service_areas table...")
    op.create_table(
        "instructor_service_areas",
        sa.Column("instructor_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "neighborhood_id", sa.String(26), sa.ForeignKey("region_boundaries.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("coverage_type", sa.String(20), nullable=True),
        sa.Column("max_distance_miles", sa.Numeric(5, 2), nullable=True),
        sa.PrimaryKeyConstraint("instructor_id", "neighborhood_id"),
    )
    op.create_index(
        "ix_instructor_service_areas_neighborhood_id",
        "instructor_service_areas",
        ["neighborhood_id"],
    )
    op.create_index(
        "ix_instructor_service_areas_instructor",
        "instructor_service_areas",
        ["instructor_id", "is_active"],
    )
    op.create_index(
        "ix_isa_instructor_coverage",
        "instructor_service_areas",
        ["instructor_id", "coverage_type"],
    )
    op.create_check_constraint(
        "ck_instructor_service_areas_coverage_type",
        "instructor_service_areas",
        "coverage_type IS NULL OR coverage_type IN ('primary','secondary','by_request')",
    )

    print("Creating instructor_preferred_places table...")
    op.create_table(
        "instructor_preferred_places",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("address", sa.String(512), nullable=False),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("place_id", sa.String(255), nullable=True),
        sa.Column("lat", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("lng", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("approx_lat", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("approx_lng", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("neighborhood", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instructor_id",
            "kind",
            "address",
            name="uq_instructor_preferred_places_instructor_kind_address",
        ),
        sa.CheckConstraint(
            "kind IN ('teaching_location','public_space')",
            name="ck_instructor_preferred_places_kind",
        ),
    )
    op.create_index(
        "ix_instructor_preferred_places_instructor_kind_position",
        "instructor_preferred_places",
        ["instructor_id", "kind", "position"],
    )

    if is_postgres:
        op.execute(
            """
            CREATE OR REPLACE FUNCTION public.update_updated_at_column()
            RETURNS TRIGGER
            SET search_path = public
            AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER instructor_preferred_places_set_updated_at
            BEFORE UPDATE ON instructor_preferred_places
            FOR EACH ROW
            EXECUTE FUNCTION public.update_updated_at_column();
            """
        )

    if is_postgres:
        op.execute("ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS embedding_v2 vector(1536)")
        op.add_column(
            "service_catalog",
            sa.Column("embedding_model", sa.Text(), nullable=True),
        )
        op.add_column(
            "service_catalog",
            sa.Column("embedding_model_version", sa.Text(), nullable=True),
        )
        op.add_column(
            "service_catalog",
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            "service_catalog",
            sa.Column("embedding_text_hash", sa.Text(), nullable=True),
        )

        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_catalog_embedding_v2
            ON service_catalog USING ivfflat (embedding_v2 vector_cosine_ops)
            WITH (lists = 100);
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_catalog_embedding_model
            ON service_catalog(embedding_model)
            WHERE embedding_v2 IS NOT NULL;
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_catalog_name_trgm
            ON service_catalog USING gin (name gin_trgm_ops);
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_catalog_description_trgm
            ON service_catalog USING gin (description gin_trgm_ops)
            WHERE description IS NOT NULL;
            """
        )

        op.execute("ALTER TABLE region_boundaries ADD COLUMN IF NOT EXISTS name_embedding vector(1536)")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_region_boundaries_name_embedding
            ON region_boundaries USING ivfflat (name_embedding vector_cosine_ops)
            WITH (lists = 100);
            """
        )

    print("Creating search_queries table...")
    op.create_table(
        "search_queries",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("normalized_query", json_type, nullable=False),
        sa.Column("parsing_mode", sa.Text(), nullable=False),
        sa.Column("parsing_latency_ms", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_check_constraint(
        "ck_search_queries_parsing_mode",
        "search_queries",
        "parsing_mode IN ('regex', 'llm', 'hybrid')",
    )
    op.create_index("idx_search_queries_created", "search_queries", ["created_at"])
    if is_postgres:
        op.execute(
            """
            CREATE INDEX idx_search_queries_created_desc
            ON search_queries (created_at DESC);
            """
        )
    op.create_index("idx_search_queries_user", "search_queries", ["user_id"])

    print("Creating search_clicks table...")
    op.create_table(
        "search_clicks",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("search_query_id", sa.String(26), sa.ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", sa.String(26), sa.ForeignKey("service_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_id", sa.String(26), sa.ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_check_constraint(
        "ck_search_clicks_action",
        "search_clicks",
        "action IN ('view', 'book', 'message', 'favorite')",
    )
    op.create_index("idx_search_clicks_query", "search_clicks", ["search_query_id"])
    op.create_index("idx_search_clicks_service", "search_clicks", ["service_id"])

    default_city_id = "01JDEFAULTNYC0000000000"
    candidate_region_ids_type = sa.ARRAY(sa.String(26)) if is_postgres else json_type

    print("Creating location_aliases table...")
    op.create_table(
        "location_aliases",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("city_id", sa.String(26), nullable=False, server_default=default_city_id),
        sa.Column("alias_normalized", sa.String(255), nullable=False),
        sa.Column(
            "region_boundary_id",
            sa.String(26),
            sa.ForeignKey("region_boundaries.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("requires_clarification", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("candidate_region_ids", candidate_region_ids_type, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("user_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("alias_type", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint(
        "uq_location_aliases_city_alias",
        "location_aliases",
        ["city_id", "alias_normalized"],
    )
    if is_postgres:
        op.execute(
            """
            CREATE INDEX idx_location_aliases_lookup
            ON location_aliases(city_id, alias_normalized)
            WHERE status != 'deprecated';
            """
        )
    else:
        op.create_index(
            "idx_location_aliases_lookup",
            "location_aliases",
            ["city_id", "alias_normalized"],
        )
    op.create_index("idx_location_aliases_status", "location_aliases", ["status"])
    op.create_check_constraint(
        "ck_location_aliases_status",
        "location_aliases",
        "status IN ('active', 'pending_review', 'deprecated')",
    )
    op.create_check_constraint(
        "ck_location_aliases_source",
        "location_aliases",
        "source IN ('manual', 'fuzzy', 'embedding', 'llm', 'user_learning')",
    )

    op.create_check_constraint(
        "location_aliases_valid_resolution",
        "location_aliases",
        "(region_boundary_id IS NOT NULL AND requires_clarification = FALSE)"
        " OR "
        "(region_boundary_id IS NULL AND requires_clarification = TRUE AND candidate_region_ids IS NOT NULL)"
        " OR "
        "(region_boundary_id IS NULL AND requires_clarification = FALSE AND candidate_region_ids IS NULL)",
    )

    print("Creating unresolved_location_queries table...")
    sample_original_queries_type = sa.ARRAY(sa.String(500)) if is_postgres else json_type
    empty_array_default = sa.text("'{}'") if is_postgres else sa.text("'[]'")
    click_region_counts_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")

    op.create_table(
        "unresolved_location_queries",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("city_id", sa.String(26), nullable=False, server_default=default_city_id),
        sa.Column("query_normalized", sa.String(255), nullable=False),
        sa.Column(
            "sample_original_queries",
            sample_original_queries_type,
            nullable=False,
            server_default=empty_array_default,
        ),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unique_user_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "click_region_counts",
            json_type,
            nullable=False,
            server_default=click_region_counts_default,
        ),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "resolved_region_boundary_id",
            sa.String(26),
            sa.ForeignKey("region_boundaries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(26), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint(
        "uq_unresolved_queries_city_query",
        "unresolved_location_queries",
        ["city_id", "query_normalized"],
    )

    if is_postgres:
        op.create_index(
            "idx_unresolved_queries_frequency",
            "unresolved_location_queries",
            [sa.text("unique_user_count DESC")],
        )
        op.create_index(
            "idx_unresolved_queries_click_count",
            "unresolved_location_queries",
            [sa.text("click_count DESC")],
        )
        op.create_index(
            "idx_unresolved_queries_status",
            "unresolved_location_queries",
            ["status"],
        )
        op.execute(
            """
            CREATE INDEX idx_unresolved_queries_unreviewed
            ON unresolved_location_queries(unique_user_count DESC)
            WHERE reviewed = FALSE;
            """
        )
    else:
        op.create_index(
            "idx_unresolved_queries_frequency",
            "unresolved_location_queries",
            ["unique_user_count"],
        )
        op.create_index(
            "idx_unresolved_queries_click_count",
            "unresolved_location_queries",
            ["click_count"],
        )
        op.create_index(
            "idx_unresolved_queries_status",
            "unresolved_location_queries",
            ["status"],
        )
        op.create_index(
            "idx_unresolved_queries_reviewed",
            "unresolved_location_queries",
            ["reviewed"],
        )

    print("Creating region_settings table...")
    op.create_table(
        "region_settings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("region_code", sa.Text(), nullable=False),
        sa.Column("region_name", sa.Text(), nullable=False),
        sa.Column("country_code", sa.Text(), nullable=False, server_default="us"),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("price_floor_in_person", sa.Integer(), nullable=False),
        sa.Column("price_floor_remote", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.Text(), nullable=False, server_default="USD"),
        sa.Column("student_fee_percent", sa.Numeric(5, 2), nullable=False, server_default="12.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_code", name="uq_region_settings_region_code"),
    )

    print("Creating price_thresholds table...")
    op.create_table(
        "price_thresholds",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("region_code", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("max_price", sa.Integer(), nullable=True),
        sa.Column("min_price", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_code", "category", "intent", name="uq_price_thresholds_region_category_intent"),
    )

    print("Seeding price_thresholds defaults...")
    op.execute(
        """
        INSERT INTO price_thresholds (id, region_code, category, intent, max_price, min_price) VALUES
          ('pt_nyc_music_budget', 'nyc', 'music', 'budget', 100, NULL),
          ('pt_nyc_music_standard', 'nyc', 'music', 'standard', 150, 100),
          ('pt_nyc_music_premium', 'nyc', 'music', 'premium', NULL, 150),
          ('pt_nyc_tutoring_budget', 'nyc', 'tutoring', 'budget', 100, NULL),
          ('pt_nyc_tutoring_standard', 'nyc', 'tutoring', 'standard', 150, 100),
          ('pt_nyc_tutoring_premium', 'nyc', 'tutoring', 'premium', NULL, 150),
          ('pt_nyc_sports_budget', 'nyc', 'sports', 'budget', 100, NULL),
          ('pt_nyc_sports_standard', 'nyc', 'sports', 'standard', 150, 100),
          ('pt_nyc_sports_premium', 'nyc', 'sports', 'premium', NULL, 150),
          ('pt_nyc_language_budget', 'nyc', 'language', 'budget', 100, NULL),
          ('pt_nyc_language_standard', 'nyc', 'language', 'standard', 150, 100),
          ('pt_nyc_language_premium', 'nyc', 'language', 'premium', NULL, 150),
          ('pt_nyc_general_budget', 'nyc', 'general', 'budget', 100, NULL),
          ('pt_nyc_general_standard', 'nyc', 'general', 'standard', 150, 100),
          ('pt_nyc_general_premium', 'nyc', 'general', 'premium', NULL, 150),
          ('pt_global_general_budget', 'global', 'general', 'budget', 80, NULL),
          ('pt_global_general_standard', 'global', 'general', 'standard', 130, 80),
          ('pt_global_general_premium', 'global', 'general', 'premium', NULL, 130)
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Drop search schema."""
    print("Dropping search schema...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    op.drop_table("price_thresholds")
    op.drop_table("region_settings")

    op.drop_table("unresolved_location_queries")

    op.drop_constraint("location_aliases_valid_resolution", "location_aliases", type_="check")
    op.drop_constraint("ck_location_aliases_source", "location_aliases", type_="check")
    op.drop_constraint("ck_location_aliases_status", "location_aliases", type_="check")
    op.drop_index("idx_location_aliases_status", table_name="location_aliases")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_location_aliases_lookup")
    else:
        op.drop_index("idx_location_aliases_lookup", table_name="location_aliases")
    op.drop_constraint("uq_location_aliases_city_alias", "location_aliases", type_="unique")
    op.drop_table("location_aliases")

    op.drop_constraint("ck_search_clicks_action", "search_clicks", type_="check")
    op.drop_index("idx_search_clicks_service", table_name="search_clicks")
    op.drop_index("idx_search_clicks_query", table_name="search_clicks")
    op.drop_table("search_clicks")

    op.drop_constraint("ck_search_queries_parsing_mode", "search_queries", type_="check")
    op.drop_index("idx_search_queries_user", table_name="search_queries")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_search_queries_created_desc")
    op.drop_index("idx_search_queries_created", table_name="search_queries")
    op.drop_table("search_queries")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_region_boundaries_name_embedding;")
        op.execute("ALTER TABLE region_boundaries DROP COLUMN IF EXISTS name_embedding;")
        op.execute("DROP INDEX IF EXISTS idx_service_catalog_embedding_v2;")
        op.execute("DROP INDEX IF EXISTS idx_service_catalog_embedding_model;")
        op.execute("DROP INDEX IF EXISTS idx_service_catalog_name_trgm;")
        op.execute("DROP INDEX IF EXISTS idx_service_catalog_description_trgm;")
        op.execute("ALTER TABLE service_catalog DROP COLUMN IF EXISTS embedding_text_hash;")
        op.execute("ALTER TABLE service_catalog DROP COLUMN IF EXISTS embedding_updated_at;")
        op.execute("ALTER TABLE service_catalog DROP COLUMN IF EXISTS embedding_model_version;")
        op.execute("ALTER TABLE service_catalog DROP COLUMN IF EXISTS embedding_model;")
        op.execute("ALTER TABLE service_catalog DROP COLUMN IF EXISTS embedding_v2;")

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS instructor_preferred_places_set_updated_at ON instructor_preferred_places;")
        op.execute("DROP FUNCTION IF EXISTS public.update_updated_at_column();")
    op.drop_index(
        "ix_instructor_preferred_places_instructor_kind_position",
        table_name="instructor_preferred_places",
    )
    op.drop_table("instructor_preferred_places")

    op.drop_constraint(
        "ck_instructor_service_areas_coverage_type",
        "instructor_service_areas",
        type_="check",
    )
    op.drop_index("ix_isa_instructor_coverage", table_name="instructor_service_areas")
    op.drop_index("ix_instructor_service_areas_instructor", table_name="instructor_service_areas")
    op.drop_index("ix_instructor_service_areas_neighborhood_id", table_name="instructor_service_areas")
    op.drop_table("instructor_service_areas")

    op.drop_index("ix_region_boundaries_name", table_name="region_boundaries")
    op.drop_index("ix_region_boundaries_region", table_name="region_boundaries")
    op.drop_index("ix_region_boundaries_type", table_name="region_boundaries")
    if is_postgres:
        op.drop_index("ix_region_boundaries_boundary", table_name="region_boundaries")
    op.drop_index("region_boundaries_rtype_rcode_idx", table_name="region_boundaries")
    op.drop_table("region_boundaries")

    op.drop_index("idx_search_event_candidates_service_created", table_name="search_event_candidates")
    op.drop_index("idx_search_event_candidates_event_position", table_name="search_event_candidates")
    op.drop_table("search_event_candidates")

    op.drop_index("idx_service_analytics_last_calculated", table_name="service_analytics")
    op.drop_index("idx_service_analytics_booking_count_30d", table_name="service_analytics")
    op.drop_index("idx_service_analytics_search_count_7d", table_name="service_analytics")
    op.drop_table("service_analytics")

    op.drop_index("idx_search_events_user_date", table_name="search_events")
    op.drop_index("idx_search_events_created_at", table_name="search_events")
    op.drop_index("idx_search_events_device_type", table_name="search_events")
    op.drop_index("idx_search_events_geo_postal", table_name="search_events")
    op.drop_index("idx_search_events_geo_borough", table_name="search_events")
    op.drop_index("idx_search_events_geo_country", table_name="search_events")
    op.drop_index("idx_search_interactions_instructor", table_name="search_interactions")
    op.drop_index("idx_search_interactions_type", table_name="search_interactions")
    op.drop_index("idx_search_interactions_event_id", table_name="search_interactions")
    op.drop_constraint("ck_search_interactions_type", "search_interactions", type_="check")
    op.drop_table("search_interactions")

    op.drop_constraint("ck_search_events_search_type", "search_events", type_="check")
    op.drop_index("idx_search_events_session_id", table_name="search_events")
    op.drop_index("idx_search_events_query", table_name="search_events")
    op.drop_index("idx_search_events_searched_at", table_name="search_events")
    op.drop_index("idx_search_events_guest_session", table_name="search_events")
    op.drop_index("idx_search_events_user_id", table_name="search_events")
    op.drop_table("search_events")

    op.drop_constraint("ck_search_history_user_or_guest", "search_history", type_="check")
    op.drop_constraint("ck_search_history_type", "search_history", type_="check")
    op.drop_index("uq_search_history_guest_normalized_query", table_name="search_history")
    op.drop_index("uq_search_history_user_normalized_query", table_name="search_history")
    op.drop_index("idx_search_history_normalized_query", table_name="search_history")
    op.drop_index("idx_search_history_conversion", table_name="search_history")
    op.drop_index("idx_search_history_guest_session", table_name="search_history")
    op.drop_index("idx_search_history_deleted", table_name="search_history")
    op.drop_index("idx_search_history_user_last_searched", table_name="search_history")
    op.drop_table("search_history")
