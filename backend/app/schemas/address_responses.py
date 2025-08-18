from typing import List

from pydantic import BaseModel


class CoverageFeatureCollectionResponse(BaseModel):
    type: str
    features: List[dict]
