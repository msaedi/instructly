# backend/tests/repositories/test_factory_taxonomy.py
"""Tests for RepositoryFactory taxonomy method."""

from app.repositories.factory import RepositoryFactory
from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository


def test_create_taxonomy_filter_repository(db):
    """Factory creates TaxonomyFilterRepository with db session."""
    repo = RepositoryFactory.create_taxonomy_filter_repository(db)
    assert repo is not None
    assert isinstance(repo, TaxonomyFilterRepository)
    assert repo.db is db
