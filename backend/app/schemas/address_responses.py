from typing import Any, Dict, List

from ._strict_base import StrictModel


class CoverageFeatureCollectionResponse(StrictModel):
    type: str
    features: List[Dict[str, Any]]

    # Maintain strict extras while satisfying legacy contract tests.
    model_config = StrictModel.model_config
