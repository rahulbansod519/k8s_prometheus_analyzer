"""JSON reporter — exports recommendations to a file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..analyzer import Recommendation

logger = logging.getLogger(__name__)


def export_json(recommendations: list[Recommendation], path: str | Path) -> None:
    """Serialise *recommendations* to a JSON file at *path*.

    The file is written atomically (write to a temp file then rename).

    Raises:
        OSError: If the file cannot be written.
    """
    out_path = Path(path)
    payload = [rec.to_dict() for rec in recommendations]
    tmp_path = out_path.with_suffix(".tmp")

    try:
        tmp_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        tmp_path.replace(out_path)
        logger.info("Results exported to %s (%d recommendations)", out_path, len(payload))
    except OSError as exc:
        logger.error("Failed to write results to %s: %s", out_path, exc)
        raise
