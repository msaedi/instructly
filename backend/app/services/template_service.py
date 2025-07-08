# backend/app/services/template_service.py
"""
Template rendering service for InstaInstru platform.

Provides centralized template rendering using Jinja2, supporting
email templates and potentially other template types in the future.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ..core.config import settings
from ..core.constants import BRAND_NAME

logger = logging.getLogger(__name__)


class TemplateService:
    """
    Centralized template rendering service using Jinja2.

    This service handles all template rendering for the platform,
    providing a consistent interface and common context variables.
    """

    def __init__(self):
        """Initialize the template service with Jinja2 environment."""
        # Get the template directory path
        template_dir = Path(__file__).parent.parent / "templates"

        # Create the Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,  # Enable autoescaping for security
            trim_blocks=True,  # Remove trailing newlines from blocks
            lstrip_blocks=True,  # Remove leading whitespace from blocks
        )

        # Add custom filters if needed
        self._register_custom_filters()

        logger.info(f"Template service initialized with template directory: {template_dir}")

    def _register_custom_filters(self):
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

    def get_common_context(self) -> Dict[str, Any]:
        """
        Get common context variables used across all templates.

        Returns:
            Dictionary of common template variables
        """
        return {
            "brand_name": BRAND_NAME,
            "current_year": datetime.now().year,
            "frontend_url": settings.frontend_url,
            "support_email": settings.from_email,
        }

    def render_template(self, template_name: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """
        Render a template with the given context.

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
            # Get the template
            template = self.env.get_template(template_name)

            # Merge contexts
            full_context = self.get_common_context()
            if context:
                full_context.update(context)
            full_context.update(kwargs)

            # Render and return
            rendered = template.render(full_context)

            logger.debug(f"Successfully rendered template: {template_name}")
            return rendered

        except TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {str(e)}")
            raise

    def render_string(self, template_string: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """
        Render a template from a string.

        Args:
            template_string: Template content as string
            context: Dictionary of template variables
            **kwargs: Additional template variables

        Returns:
            Rendered template as string
        """
        try:
            # Create template from string
            template = self.env.from_string(template_string)

            # Merge contexts
            full_context = self.get_common_context()
            if context:
                full_context.update(context)
            full_context.update(kwargs)

            # Render and return
            return template.render(full_context)

        except Exception as e:
            logger.error(f"Error rendering template string: {str(e)}")
            raise

    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template exists.

        Args:
            template_name: Path to template relative to templates directory

        Returns:
            True if template exists, False otherwise
        """
        try:
            self.env.get_template(template_name)
            return True
        except TemplateNotFound:
            return False


# Create a singleton instance for easy import
template_service = TemplateService()
