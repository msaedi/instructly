# backend/tests/test_nls_specific_service.py
"""
Tests for NLS (Natural Language Search) specific service matching behavior.

These tests verify that specific service queries return ONLY instructors
who teach that specific service, not all instructors in the category.
"""

import pytest
from fastapi.testclient import TestClient
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User


class TestNLSSpecificServiceMatching:
    """Test that specific service queries return only instructors teaching that service."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, db: Session):
        """Create test data for service-specific search tests."""
        # Check if Music category exists, create if not
        music_category = db.query(ServiceCategory).filter_by(slug="music").first()
        if not music_category:
            music_category = ServiceCategory(name="Music", slug="music", description="Music instruction services")
            db.add(music_category)
            db.flush()
        else:
            # Clean up existing test data
            db.query(InstructorService).filter(
                InstructorService.instructor_profile.has(
                    InstructorProfile.user.has(User.email.in_(["piano@test.com", "guitar@test.com", "drums@test.com"]))
                )
            ).delete(synchronize_session=False)

            db.query(InstructorProfile).filter(
                InstructorProfile.user.has(User.email.in_(["piano@test.com", "guitar@test.com", "drums@test.com"]))
            ).delete(synchronize_session=False)

            db.query(User).filter(User.email.in_(["piano@test.com", "guitar@test.com", "drums@test.com"])).delete()

            db.flush()

        # Load embedding model for test services
        model = SentenceTransformer("all-MiniLM-L6-v2")

        # Helper function to generate embedding text
        def generate_service_text(service_name, description, search_terms):
            parts = [service_name, f"Category: Music", description]
            if search_terms:
                parts.append(f"Keywords: {', '.join(search_terms)}")
            return " ".join(parts)

        # Get or create service catalog entries
        piano_service = db.query(ServiceCatalog).filter_by(name="Piano", category_id=music_category.id).first()
        if not piano_service:
            # Generate embedding for piano service
            piano_text = generate_service_text("Piano", "Piano lessons", ["piano", "keyboard", "keys"])
            piano_embedding = model.encode([piano_text])[0].tolist()

            piano_service = ServiceCatalog(
                name="Piano",
                category_id=music_category.id,
                description="Piano lessons",
                search_terms=["piano", "keyboard", "keys"],
                is_active=True,
                embedding=piano_embedding,
            )
            db.add(piano_service)
            db.flush()
        elif piano_service.embedding is None:
            # Update existing service with embedding
            piano_text = generate_service_text(
                "Piano",
                piano_service.description or "Piano lessons",
                piano_service.search_terms or ["piano", "keyboard", "keys"],
            )
            piano_service.embedding = model.encode([piano_text])[0].tolist()
            db.flush()

        guitar_service = db.query(ServiceCatalog).filter_by(name="Guitar", category_id=music_category.id).first()
        if not guitar_service:
            # Generate embedding for guitar service
            guitar_text = generate_service_text(
                "Guitar", "Guitar lessons", ["guitar", "acoustic guitar", "electric guitar"]
            )
            guitar_embedding = model.encode([guitar_text])[0].tolist()

            guitar_service = ServiceCatalog(
                name="Guitar",
                category_id=music_category.id,
                description="Guitar lessons",
                search_terms=["guitar", "acoustic guitar", "electric guitar"],
                is_active=True,
                embedding=guitar_embedding,
            )
            db.add(guitar_service)
            db.flush()
        elif guitar_service.embedding is None:
            # Update existing service with embedding
            guitar_text = generate_service_text(
                "Guitar",
                guitar_service.description or "Guitar lessons",
                guitar_service.search_terms or ["guitar", "acoustic guitar", "electric guitar"],
            )
            guitar_service.embedding = model.encode([guitar_text])[0].tolist()
            db.flush()

        drums_service = db.query(ServiceCatalog).filter_by(name="Drums", category_id=music_category.id).first()
        if not drums_service:
            # Generate embedding for drums service
            drums_text = generate_service_text("Drums", "Drum lessons", ["drums", "percussion", "drumming"])
            drums_embedding = model.encode([drums_text])[0].tolist()

            drums_service = ServiceCatalog(
                name="Drums",
                category_id=music_category.id,
                description="Drum lessons",
                search_terms=["drums", "percussion", "drumming"],
                is_active=True,
                embedding=drums_embedding,
            )
            db.add(drums_service)
            db.flush()
        elif drums_service.embedding is None:
            # Update existing service with embedding
            drums_text = generate_service_text(
                "Drums",
                drums_service.description or "Drum lessons",
                drums_service.search_terms or ["drums", "percussion", "drumming"],
            )
            drums_service.embedding = model.encode([drums_text])[0].tolist()
            db.flush()

        # Create instructors with dummy hashed password
        # Using a dummy hash - in real tests this would come from proper password hashing
        dummy_hash = "$2b$12$dummy.hash.for.testing.only.not.real.password.hash"
        piano_user = User(
            email="piano@test.com",
            full_name="Piano Teacher",
            account_status="active",
            hashed_password=dummy_hash,
            role="instructor",
        )
        guitar_user = User(
            email="guitar@test.com",
            full_name="Guitar Teacher",
            account_status="active",
            hashed_password=dummy_hash,
            role="instructor",
        )
        drums_user = User(
            email="drums@test.com",
            full_name="Drums Teacher",
            account_status="active",
            hashed_password=dummy_hash,
            role="instructor",
        )
        db.add_all([piano_user, guitar_user, drums_user])
        db.flush()

        # Create instructor profiles
        piano_profile = InstructorProfile(user_id=piano_user.id, bio="Expert piano instructor")
        guitar_profile = InstructorProfile(user_id=guitar_user.id, bio="Expert guitar instructor")
        drums_profile = InstructorProfile(user_id=drums_user.id, bio="Expert drums instructor")
        db.add_all([piano_profile, guitar_profile, drums_profile])
        db.flush()

        # Create instructor services with prices
        piano_instructor_service = InstructorService(
            instructor_profile_id=piano_profile.id,
            service_catalog_id=piano_service.id,
            hourly_rate=75.0,
            is_active=True,
        )
        guitar_instructor_service = InstructorService(
            instructor_profile_id=guitar_profile.id,
            service_catalog_id=guitar_service.id,
            hourly_rate=60.0,
            is_active=True,
        )
        drums_instructor_service = InstructorService(
            instructor_profile_id=drums_profile.id,
            service_catalog_id=drums_service.id,
            hourly_rate=65.0,
            is_active=True,
        )
        db.add_all([piano_instructor_service, guitar_instructor_service, drums_instructor_service])
        db.commit()

        # Store IDs for tests
        self.piano_service_id = piano_service.id
        self.guitar_service_id = guitar_service.id
        self.drums_service_id = drums_service.id
        self.piano_user_id = piano_user.id
        self.guitar_user_id = guitar_user.id
        self.drums_user_id = drums_user.id

    def test_specific_service_query_piano_under_80(self, client: TestClient):
        """Test that 'piano under $80' returns ONLY piano instructors."""
        response = client.get("/api/search/instructors", params={"q": "piano under $80"})

        assert response.status_code == 200
        data = response.json()

        # Should have results
        assert len(data["results"]) > 0

        # All results should be piano instructors only
        for result in data["results"]:
            assert result["service"]["id"] == self.piano_service_id
            assert result["service"]["name"].lower() == "piano"
            assert result["offering"]["hourly_rate"] <= 80

        # Should NOT include guitar or drums instructors
        instructor_ids = [r["instructor"]["id"] for r in data["results"]]
        assert self.guitar_user_id not in instructor_ids
        assert self.drums_user_id not in instructor_ids

    def test_specific_service_query_guitar(self, client: TestClient):
        """Test that 'guitar lessons' returns ONLY guitar instructors."""
        response = client.get("/api/search/instructors", params={"q": "guitar lessons"})

        assert response.status_code == 200
        data = response.json()

        # All results should be guitar instructors only
        for result in data["results"]:
            assert result["service"]["id"] == self.guitar_service_id
            assert result["service"]["name"].lower() == "guitar"

    def test_category_query_music_lessons(self, client: TestClient):
        """Test that 'music lessons' returns ALL music instructors."""
        response = client.get("/api/search/instructors", params={"q": "music lessons"})

        assert response.status_code == 200
        data = response.json()

        # Should return multiple different music services
        {r["service"]["id"] for r in data["results"]}
        service_names = {r["service"]["name"].lower() for r in data["results"]}

        # Should include multiple music services (not just one)
        assert len(service_names) >= 2  # At least 2 different services

    def test_category_query_music_under_70(self, client: TestClient):
        """Test that 'music lessons under $70' returns multiple music instructors under $70."""
        response = client.get("/api/search/instructors", params={"q": "music lessons under $70"})

        assert response.status_code == 200
        data = response.json()

        # Should return guitar ($60) and drums ($65) but not piano ($75)
        instructor_ids = [r["instructor"]["id"] for r in data["results"]]

        assert self.guitar_user_id in instructor_ids  # $60
        assert self.drums_user_id in instructor_ids  # $65
        assert self.piano_user_id not in instructor_ids  # $75 > $70

    def test_generic_query_lessons_under_70(self, client: TestClient):
        """Test that generic 'lessons under $70' returns all instructors under $70."""
        response = client.get("/api/search/instructors", params={"q": "lessons under $70"})

        assert response.status_code == 200
        data = response.json()

        # Should return all instructors under $70 regardless of service
        for result in data["results"]:
            assert result["offering"]["hourly_rate"] <= 70

    @pytest.mark.skip(
        reason="Multi-service 'OR' queries not implemented yet - requires query parser enhancement to handle boolean logic"
    )
    def test_multiple_service_query(self, client: TestClient):
        """Test that 'piano or guitar' returns both piano AND guitar instructors."""
        response = client.get("/api/search/instructors", params={"q": "piano or guitar"})

        assert response.status_code == 200
        data = response.json()

        service_names = {r["service"]["name"].lower() for r in data["results"]}

        # Should include both piano and guitar
        assert "piano" in service_names
        assert "guitar" in service_names
        # But not drums
        assert "drums" not in service_names

    @pytest.mark.skip(
        reason="Price-only queries without service/category not implemented - requires fallback to browse all instructors with price filter"
    )
    def test_no_service_price_constraint_only(self, client: TestClient):
        """Test that 'under $65' returns all services under $65."""
        response = client.get("/api/search/instructors", params={"q": "under $65"})

        assert response.status_code == 200
        data = response.json()

        # Should return guitar ($60) but not drums ($65) or piano ($75)
        instructor_ids = [r["instructor"]["id"] for r in data["results"]]

        assert self.guitar_user_id in instructor_ids  # $60 < $65
        # Note: $65 might be included depending on implementation (<=)
