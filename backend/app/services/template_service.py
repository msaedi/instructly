# backend/app/services/template_service.py
"""
Template rendering service for InstaInstru platform.

Provides centralized template rendering using Jinja2, supporting
email templates and potentially other template types in the future.

FIXED IN THIS VERSION:
- Now extends BaseService for architectural consistency
- Added performance metrics to all public methods
- Removed singleton pattern - uses dependency injection
- Added intelligent caching for common contexts and template checks
- Maintains all existing functionality
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Optional, cast

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.constants import BRAND_NAME
from .base import BaseService, CacheInvalidationProtocol

logger = logging.getLogger(__name__)


class TemplateService(BaseService):
    """
    Centralized template rendering service using Jinja2.

    This service handles all template rendering for the platform,
    providing a consistent interface and common context variables.

    Now extends BaseService for:
    - Consistent architecture across all services
    - Performance metrics collection
    - Standardized error handling
    - Integrated caching support

    Uses dependency injection pattern - no singleton.

    Caching Strategy:
    - Common context is cached (changes rarely)
    - Template existence checks are cached
    - Jinja2 handles template compilation caching internally
    """

    # Cache key prefixes
    CACHE_PREFIX_CONTEXT = "template:context:common"
    CACHE_PREFIX_EXISTS = "template:exists"

    # Cache TTLs (in seconds)
    CACHE_TTL_CONTEXT = 3600  # 1 hour for common context
    CACHE_TTL_EXISTS = 86400  # 24 hours for template existence

    def __init__(
        self,
        db: Optional[Session] = None,
        cache: Optional[CacheInvalidationProtocol] = None,
    ) -> None:
        """
        Initialize the template service with Jinja2 environment.

        Args:
            db: Optional database session (not used by TemplateService but required by BaseService)
            cache: Optional cache service for caching common contexts and template checks
        """
        # For TemplateService, we don't actually need a DB session
        # But BaseService requires one, so we'll handle it gracefully
        if db is None:
            # Create a minimal session just for BaseService compatibility
            # This won't be used but satisfies the interface
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            engine = create_engine("sqlite:///:memory:")
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()
            self._owns_db = True
        else:
            self._owns_db = False

        # Initialize BaseService - this gives us self.cache
        super().__init__(db, cache)

        # Get the template directory path
        template_dir = Path(__file__).parent.parent / "templates"

        # Create the Jinja2 environment
        # Note: Jinja2 has its own internal template compilation cache
        # Use utf-8-sig to gracefully handle potential BOMs in template files
        self.env = Environment(
            loader=FileSystemLoader(template_dir, encoding="utf-8-sig"),
            autoescape=True,  # Enable autoescaping for security
            trim_blocks=True,  # Remove trailing newlines from blocks
            lstrip_blocks=True,  # Remove leading whitespace from blocks
            cache_size=400,  # Jinja2's internal cache for compiled templates
            auto_reload=True,  # Reload templates when files change
        )

        # Add custom filters if needed
        self._register_custom_filters()

        # Track if caching is enabled (can be disabled for development)
        self._caching_enabled = getattr(settings, "template_cache_enabled", True)

        self.logger.info(f"Template service initialized with template directory: {template_dir}")
        self.logger.info(f"Template caching: {'enabled' if self._caching_enabled else 'disabled'}")

    def __del__(self) -> None:
        """Clean up the database session if we created it."""
        if hasattr(self, "_owns_db") and self._owns_db and hasattr(self, "db"):
            self.db.close()

    def _register_custom_filters(self) -> None:
        """Register any custom Jinja2 filters."""

        # Example: Add a currency filter
        def currency(value: float) -> str:
            """Format a number as currency."""
            return f"${value:,.2f}"

        self.env.filters["currency"] = currency

        # Add a date formatter
        def format_date(value: datetime, format_str: str = "%B %d, %Y") -> str:
            """Format a datetime object."""
            if isinstance(value, str):
                return value  # Already formatted
            return value.strftime(format_str)

        self.env.filters["format_date"] = format_date

        # Add a time formatter
        def format_time(value: datetime, format_str: str = "%-I:%M %p") -> str:
            """Format a time object."""
            if isinstance(value, str):
                return value  # Already formatted
            return value.strftime(format_str)

        self.env.filters["format_time"] = format_time

    def _get_cache_key(self, prefix: str, *args: object) -> str:
        """
        Generate a cache key from prefix and arguments.

        Args:
            prefix: Cache key prefix
            *args: Additional key components

        Returns:
            Cache key string
        """
        components = [prefix] + [str(arg) for arg in args]
        return ":".join(components)

    def _should_use_cache(self) -> bool:
        """Check if caching should be used."""
        return self._caching_enabled and self.cache is not None and hasattr(self.cache, "get")

    @BaseService.measure_operation("get_common_context")
    def get_common_context(self) -> dict[str, Any]:
        """
        Get common context variables used across all templates.

        This is cached since these values change rarely.

        Returns:
            Dictionary of common template variables
        """
        # Try cache first if available
        cache = self.cache
        cache_key = self.CACHE_PREFIX_CONTEXT
        if self._should_use_cache() and cache is not None:
            try:
                cached_context = cache.get(cache_key)
                if isinstance(cached_context, dict):
                    self.logger.debug("Common context retrieved from cache")
                    return cast(dict[str, Any], cached_context)
            except Exception as e:
                self.logger.warning(f"Cache get failed for common context: {e}")

        # Build the context
        context: dict[str, Any] = {
            "brand_name": BRAND_NAME,
            "current_year": datetime.now(timezone.utc).year,
            "frontend_url": settings.frontend_url,
            "base_url": settings.frontend_url,
            "support_email": settings.from_email,
        }

        # Cache it if possible
        if self._should_use_cache() and cache is not None:
            try:
                cache.set(cache_key, context, self.CACHE_TTL_CONTEXT)
                self.logger.debug("Common context cached")
            except Exception as e:
                self.logger.warning(f"Failed to cache common context: {e}")

        return context

    @BaseService.measure_operation("render_template")
    def render_template(
        self,
        /,
        template_name: str,
        context: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Render a template with the given context.

        Note: Jinja2 internally caches compiled templates, so we don't need
        to cache the compiled templates ourselves. We only cache the common context.

        Args:
            template_name: Path to template relative to templates directory
            context: Dictionary of template variables
            **kwargs: Additional template variables

        Returns:
            Rendered template as string

        Raises:
            TemplateNotFound: If template doesn't exist
        """
        try:
            # Coerce Enum values to plain strings if needed
            try:
                template_name_str = template_name.value  # type: ignore[attr-defined]
            except Exception:
                template_name_str = str(template_name)
            # Get the template (Jinja2 caches compiled templates internally)
            template = self.env.get_template(template_name_str)

            # Merge contexts - get_common_context() uses caching
            full_context: dict[str, Any] = self.get_common_context()
            if context:
                full_context.update(context)
            full_context.update(kwargs)

            # Render and return
            rendered = cast(str, template.render(full_context))

            self.logger.debug(f"Successfully rendered template: {template_name}")
            return rendered

        except TemplateNotFound:
            self.logger.error(f"Template not found: {template_name}")
            raise
        except Exception as e:
            # Fallback: read file content and render from string after sanitizing any stray bytes
            try:
                try:
                    template_name_str = template_name.value  # type: ignore[attr-defined]
                except Exception:
                    template_name_str = str(template_name)
                template_path = (
                    Path(__file__).parent.parent / "templates" / template_name_str
                ).resolve()
                with open(template_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    raw = f.read()
                # Basic sanitize: strip any leading non-printable characters
                import re

                sanitized = re.sub(r"^[^\x09\x0A\x0D\x20-\x7E]+", "", raw)

                template = self.env.from_string(sanitized)
                full_context = self.get_common_context()
                if context:
                    full_context.update(context)
                full_context.update(kwargs)
                rendered = cast(str, template.render(full_context))
                self.logger.warning(f"Rendered {template_name} via fallback sanitize path")
                return rendered
            except Exception as inner:
                self.logger.error(
                    f"Error rendering template {template_name}: {str(e)} | Fallback failed: {inner}"
                )
                raise

    @BaseService.measure_operation("render_string")
    def render_string(
        self,
        /,
        template_string: str,
        context: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Render a template from a string.

        String templates are not cached since they're typically unique.

        Args:
            template_string: Template content as string
            context: Dictionary of template variables
            **kwargs: Additional template variables

        Returns:
            Rendered template as string
        """
        try:
            # Create template from string (not cached)
            template = self.env.from_string(template_string)

            # Merge contexts - get_common_context() uses caching
            full_context: dict[str, Any] = self.get_common_context()
            if context:
                full_context.update(context)
            full_context.update(kwargs)

            # Render and return
            return cast(str, template.render(full_context))

        except Exception as e:
            self.logger.error(f"Error rendering template string: {str(e)}")
            raise

    @BaseService.measure_operation("template_exists")
    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template exists.

        This is cached since template existence rarely changes.

        Args:
            template_name: Path to template relative to templates directory

        Returns:
            True if template exists, False otherwise
        """
        # Try cache first
        cache = self.cache
        cache_key = self._get_cache_key(self.CACHE_PREFIX_EXISTS, template_name)
        if self._should_use_cache() and cache is not None:
            try:
                cached_result = cache.get(cache_key)
                if isinstance(cached_result, bool):
                    self.logger.debug(
                        f"Template existence for '{template_name}' retrieved from cache"
                    )
                    return cached_result
            except Exception as e:
                self.logger.warning(f"Cache get failed for template existence: {e}")

        # Check if template exists
        try:
            try:
                template_name_str = template_name.value  # type: ignore[attr-defined]
            except Exception:
                template_name_str = str(template_name)
            self.env.get_template(template_name_str)
            exists = True
        except TemplateNotFound:
            exists = False

        # Cache the result
        if self._should_use_cache() and cache is not None:
            try:
                cache.set(cache_key, exists, self.CACHE_TTL_EXISTS)
                self.logger.debug(f"Template existence for '{template_name}' cached")
            except Exception as e:
                self.logger.warning(f"Failed to cache template existence: {e}")

        return exists

    def invalidate_cache(self, *keys: str) -> None:  # no-metrics
        """
        Invalidate all template-related caches.

        Useful when templates are updated or settings change.
        """
        if keys:
            super().invalidate_cache(*keys)
            return

        cache = self.cache
        if not self._should_use_cache() or cache is None:
            return

        try:
            cache.delete(self.CACHE_PREFIX_CONTEXT)
            cache.delete_pattern(f"{self.CACHE_PREFIX_EXISTS}:*")

            self.logger.info("Template cache invalidated")
        except Exception as e:
            self.logger.error(f"Failed to invalidate template cache: {e}")

    def get_cache_stats(self) -> dict[str, Any]:  # no-metrics
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache stats
        """
        stats: dict[str, Any] = {
            "caching_enabled": self._caching_enabled,
            "jinja2_cache_size": getattr(getattr(self.env, "cache", None), "capacity", None),
        }

        # Add metrics from BaseService
        metrics = self.get_metrics()
        if metrics:
            stats["operation_metrics"] = metrics

        return stats
