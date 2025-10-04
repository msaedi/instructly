from typing import Any, Dict, List

from pydantic import BaseModel

from ._strict_base import StrictModel


class CoverageFeatureCollectionResponse(BaseModel):
    type: str
    features: List[Dict[str, Any]]

    # Maintain strict extras while satisfying legacy contract tests.
    model_config = StrictModel.model_config
