from pydantic import BaseModel

class StrictModel(BaseModel):
    ...


class StrictRequestModel(StrictModel):
    ...
