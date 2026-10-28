from typing import Protocol, Sequence

import numpy as np
import numpy.typing as npt


class Embedder(Protocol):
    key: str
    model: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]: ...
