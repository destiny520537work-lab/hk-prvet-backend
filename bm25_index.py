"""
BM25 full-text index over PDF chunks.

Usage:
    idx = BM25Index()
    idx.build(chunks)               # chunks from doc_parser
    hits = idx.search("2012-03-14") # returns top-k chunks with bbox
"""

from __future__ import annotations

import re
from typing import Any

from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    try:
        import jieba
        return list(jieba.cut(text.lower()))
    except ImportError:
        pass
    return re.findall(r"\w+", text.lower())


def bbox_to_highlight_box(bbox: list[float]) -> dict[str, float]:
    """Convert Azure DI bbox [x0,y0,x1,y1] in [0,1000] to frontend HighlightBox."""
    return {
        "x":      round(bbox[0] / 10, 2),
        "y":      round(bbox[1] / 10, 2),
        "width":  round((bbox[2] - bbox[0]) / 10, 2),
        "height": round((bbox[3] - bbox[1]) / 10, 2),
    }


class BM25Index:
    def __init__(self) -> None:
        self._chunks: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None

    def build(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks
        self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in chunks])

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self._bm25 or not self._chunks:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score <= 0:
                continue
            chunk = dict(self._chunks[idx])
            chunk["score"] = round(float(score), 4)
            results.append(chunk)
        return results

    def find_best_bbox(self, query: str, fallback_box: dict) -> tuple[dict, str]:
        """
        Search for query, return (highlight_box, source_type).
        Falls back to fallback_box if no good match found.
        """
        hits = self.search(query, top_k=1)
        if hits and hits[0]["score"] > 0.3:
            best = hits[0]
            return bbox_to_highlight_box(best["bbox"]), best["type"]
        return fallback_box, "paragraph"
