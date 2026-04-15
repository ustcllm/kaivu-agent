from .base import ScientificTask, TaskAdapter, TaskAdapterResult
from .kaggle import KaggleTaskAdapter

__all__ = [
    "KaggleTaskAdapter",
    "ScientificTask",
    "TaskAdapter",
    "TaskAdapterResult",
]
