from typing import Any, Dict, List

from pydantic import BaseModel


class CoverageFeatureCollectionResponse(BaseModel):
    type: str
    features: List[Dict[str, Any]]
