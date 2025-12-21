# Infrastructure routes (intentionally unversioned)
# All application routes are in v1/
from . import (
    alerts as alerts,
    gated as gated,
    internal as internal,
    metrics as metrics,
    monitoring as monitoring,
    prometheus as prometheus,
    ready as ready,
)
