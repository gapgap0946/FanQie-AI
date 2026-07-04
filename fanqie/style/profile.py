"""StyleProfile data model."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class StyleProfile:
    """???? ? ?????????????????."""
    avg_sentence_length: float = 0.0
    sentence_length_stddev: float = 0.0
    avg_paragraph_length: int = 0
    paragraph_length_range: tuple[int, int] = (0, 0)
    vocabulary_diversity: float = 0.0
    top_patterns: list[str] = field(default_factory=list)
    rhetorical_features: list[str] = field(default_factory=list)
    source_name: str | None = None
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["paragraph_length_range"] = list(self.paragraph_length_range)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StyleProfile":
        pr = data.get("paragraph_length_range", [0, 0])
        if isinstance(pr, list) and len(pr) == 2:
            data["paragraph_length_range"] = tuple(pr)
        else:
            data["paragraph_length_range"] = (0, 0)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
