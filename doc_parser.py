"""
Azure Document Intelligence PDF parser.

parse_pdf(pdf_path) -> list[Chunk]
  Chunk = {text, page_idx, bbox: [x0,y0,x1,y1] in [0,1000], type: "paragraph"|"table_cell"}

Caches results to cache/{stem}.json to avoid repeated API calls.
Falls back gracefully if Azure credentials are missing.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

TIMEOUT_SECONDS = 600


async def parse_pdf(pdf_path: str, force: bool = False) -> list[dict[str, Any]]:
    """Parse PDF via Azure DI. Returns list of chunks with bbox in [0,1000]."""
    stem = Path(pdf_path).stem
    cache_file = CACHE_DIR / f"{stem}.json"

    if not force and cache_file.exists():
        chunks = json.loads(cache_file.read_text(encoding="utf-8"))
        print(f"[doc_parser] cache hit: {stem} ({len(chunks)} chunks)")
        return chunks

    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    if not endpoint or not key:
        raise RuntimeError(
            "Azure DI credentials not set. "
            "Ensure AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
            "AZURE_DOCUMENT_INTELLIGENCE_KEY are in .env"
        )

    import azure.ai.documentintelligence as di
    import azure.core.credentials as creds

    pdf_bytes = Path(pdf_path).read_bytes()
    client = di.DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=creds.AzureKeyCredential(key),
    )
    request = di.models.AnalyzeDocumentRequest(bytes_source=pdf_bytes)
    poller = await asyncio.to_thread(
        client.begin_analyze_document,
        "prebuilt-layout",
        body=request,
        output_content_format="markdown",
    )
    result = await asyncio.to_thread(poller.result, timeout=TIMEOUT_SECONDS)

    chunks = _to_chunks(result)
    cache_file.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[doc_parser] parsed {stem}: {len(chunks)} chunks, cached to {cache_file.name}")
    return chunks


def load_from_cache(pdf_stem: str) -> list[dict[str, Any]] | None:
    """Load cached chunks if they exist, else return None."""
    cache_file = CACHE_DIR / f"{pdf_stem}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    return None


def _to_chunks(result) -> list[dict[str, Any]]:
    page_dims: dict[int, tuple[float, float]] = {}
    for page in result.pages:
        page_dims[page.page_number] = (page.width or 8.5, page.height or 11.0)

    chunks: list[dict[str, Any]] = []
    table_bboxes_by_page: dict[int, list[list[float]]] = {}

    for table in result.tables or []:
        for cell in table.cells or []:
            if not cell.content or not cell.bounding_regions:
                continue
            region = cell.bounding_regions[0]
            page_num = region.page_number
            w, h = page_dims.get(page_num, (8.5, 11.0))
            bbox = _poly_to_bbox(region.polygon, w, h)
            if bbox is None:
                continue
            table_bboxes_by_page.setdefault(page_num, []).append(bbox)
            chunks.append({"text": cell.content.strip(), "page_idx": page_num - 1, "bbox": bbox, "type": "table_cell"})

    for para in result.paragraphs or []:
        if not para.content or not para.bounding_regions:
            continue
        region = para.bounding_regions[0]
        page_num = region.page_number
        w, h = page_dims.get(page_num, (8.5, 11.0))
        bbox = _poly_to_bbox(region.polygon, w, h)
        if bbox is None:
            continue
        if any(_iou(bbox, tb) > 0.5 for tb in table_bboxes_by_page.get(page_num, [])):
            continue
        text = para.content.strip()
        if text:
            chunks.append({"text": text, "page_idx": page_num - 1, "bbox": bbox, "type": "paragraph"})

    return chunks


def _poly_to_bbox(polygon, pw: float, ph: float) -> list[float] | None:
    if not polygon or len(polygon) < 2:
        return None
    xs = [p for i, p in enumerate(polygon) if i % 2 == 0]
    ys = [p for i, p in enumerate(polygon) if i % 2 == 1]
    if not xs or not ys:
        return None
    return [
        round(min(xs) / pw * 1000, 1),
        round(min(ys) / ph * 1000, 1),
        round(max(xs) / pw * 1000, 1),
        round(max(ys) / ph * 1000, 1),
    ]


def _iou(a: list[float], b: list[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter == 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
