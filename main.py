"""
HK PreVet Demo — FastAPI backend.

Endpoints:
  POST /api/demo/process       trigger Azure DI processing of 6 demo PDFs
  GET  /api/demo/status        poll processing status
  GET  /api/demo/points        23 extracted data points (matches frontend ExtractedPoint type)
  GET  /api/demo/background    background check results
  GET  /api/demo/kg            KG graph data (nodes / edges / riskPaths)
  GET  /api/pdf/{filename}     serve a demo PDF file
  GET  /api/corpus             list of real Chinese procurement documents
  GET  /api/corpus/{filename}  serve a corpus PDF
  GET  /api/corpus/{filename}/chunks  extracted chunks from Azure DI

Run:
  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

load_dotenv(Path(__file__).parent / ".env")

from bm25_index import BM25Index
from doc_parser import load_from_cache, parse_pdf
from field_rules import DOC_SOURCE_TYPE, FIELD_RULES
from kg_service import get_kg

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).parent
_pdf_docs_env = os.environ.get("PDF_DOCS_PATH", "../hk-prvet-demo/dist/docs")
PDF_DOCS_DIR = (BACKEND_DIR / _pdf_docs_env).resolve()

SEARCH_RESULTS_PATH = (
    BACKEND_DIR / "../hk-prvet-demo/src/data/searchResults.json"
).resolve()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

# filename -> BM25Index
_indexes: dict[str, BM25Index] = {}
_status = {"state": "idle", "progress": 0, "message": "Not started"}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="HK PreVet Demo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: pre-load cached indexes
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    _check_config()
    _preload_cached_indexes()


def _check_config() -> None:
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    if not endpoint or not key:
        print("[startup] WARNING: Azure DI credentials not set — will use fallback bboxes")
    else:
        print(f"[startup] Azure DI configured: {endpoint}")
    if not PDF_DOCS_DIR.exists():
        print(f"[startup] WARNING: PDF_DOCS_DIR not found: {PDF_DOCS_DIR}")
    else:
        pdfs = list(PDF_DOCS_DIR.glob("*.pdf"))
        print(f"[startup] PDF_DOCS_DIR: {PDF_DOCS_DIR} ({len(pdfs)} PDFs found)")


def _preload_cached_indexes() -> None:
    loaded = 0
    for rule in FIELD_RULES:
        filename = rule["doc_filename"]
        if filename in _indexes:
            continue
        stem = Path(filename).stem
        chunks = load_from_cache(stem)
        if chunks:
            idx = BM25Index()
            idx.build(chunks)
            _indexes[filename] = idx
            loaded += 1
    if loaded:
        print(f"[startup] Loaded {loaded} BM25 index(es) from cache")
        _status["state"] = "ready"
        _status["progress"] = 100
        _status["message"] = "Ready (loaded from cache)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_path(filename: str) -> Path:
    return PDF_DOCS_DIR / Path(filename).name


def _build_points() -> list[dict]:
    """
    Build the 23 extracted data points.
    For each field rule:
      - If BM25 index exists: search for the field, get real bbox
      - Otherwise: use fallback_box from field_rules.py
    """
    points = []
    for rule in FIELD_RULES:
        filename = rule["doc_filename"]
        fallback_box = rule["fallback_box"]
        source_type = DOC_SOURCE_TYPE.get(rule["doc_id"], "doc")

        highlight_box = fallback_box
        # Try to get real bbox from BM25 index
        idx = _indexes.get(filename)
        if idx:
            found_box, chunk_type = idx.find_best_bbox(rule["bm25_query"], fallback_box)
            highlight_box = found_box
            # Override source_type with Azure DI chunk type if it's a table cell
            if chunk_type == "table_cell":
                source_type = "table"

        point: dict = {
            "id": rule["id"],
            "category": rule["category"],
            "label": rule["label"],
            "extractedValue": rule["extracted_value"],
            "expectedValue": rule["expected_value"],
            "status": rule["status"],
            "sourceType": source_type,
            "sourceDocId": rule["doc_id"],
            "pageNumber": 1,
            "highlightBox": highlight_box,
        }
        if rule.get("risk_note"):
            point["riskNote"] = rule["risk_note"]

        points.append(point)

    return points


# ---------------------------------------------------------------------------
# Background processing task
# ---------------------------------------------------------------------------

async def _process_pdfs() -> None:
    global _status
    _status = {"state": "processing", "progress": 0, "message": "Starting..."}

    unique_filenames = list({r["doc_filename"] for r in FIELD_RULES})
    total = len(unique_filenames)

    for i, filename in enumerate(unique_filenames):
        if filename in _indexes:
            _status["progress"] = int((i + 1) / total * 100)
            continue

        pdf_path = _pdf_path(filename)
        if not pdf_path.exists():
            print(f"[process] PDF not found: {pdf_path}")
            _status["progress"] = int((i + 1) / total * 100)
            continue

        _status["message"] = f"Processing {filename}..."
        try:
            chunks = await parse_pdf(str(pdf_path))
            idx = BM25Index()
            idx.build(chunks)
            _indexes[filename] = idx
        except RuntimeError as e:
            print(f"[process] {filename} failed: {e} — using fallback")

        _status["progress"] = int((i + 1) / total * 100)

    _status["state"] = "ready"
    _status["progress"] = 100
    _status["message"] = "Processing complete"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/demo/process")
async def demo_process():
    """Trigger Azure DI processing of the 6 demo PDFs (async)."""
    if _status["state"] == "processing":
        return {"status": "already_processing", "message": "Processing in progress"}
    asyncio.create_task(_process_pdfs())
    return {"status": "started", "message": "Processing started"}


@app.get("/api/demo/status")
async def demo_status():
    """Poll processing status."""
    return _status


@app.get("/api/demo/points")
async def demo_points():
    """
    Return the 23 extracted data points in the format expected by the frontend.
    Compatible with src/types/extraction.ts ExtractedPoint interface.
    """
    return _build_points()


@app.get("/api/demo/background")
async def demo_background():
    """Return background check results from the existing mock JSON."""
    if not SEARCH_RESULTS_PATH.exists():
        raise HTTPException(status_code=404, detail="searchResults.json not found")
    return json.loads(SEARCH_RESULTS_PATH.read_text(encoding="utf-8"))


@app.get("/api/demo/kg")
async def demo_kg():
    """Return KG graph data: nodes, edges, and pre-computed risk paths."""
    return get_kg().get_graph_data()


@app.get("/api/pdf/{filename}")
async def serve_pdf(filename: str):
    """Serve a demo PDF file."""
    safe_name = Path(filename).name
    pdf_path = PDF_DOCS_DIR / safe_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found: {safe_name}")
    return FileResponse(str(pdf_path), media_type="application/pdf")


# ---------------------------------------------------------------------------
# Corpus endpoints — real Chinese medical procurement documents
# ---------------------------------------------------------------------------

CORPUS_META = [
    {
        "id": "medical_device_bid",
        "filename": "medical_device_bid.pdf",
        "title": "湖州市一人民医院医械招标 — 投标文件",
        "description": "医疗器械采购投标书，含麻醉气体监护仪、高频射频刀等设备",
        "company": "合肥诺和电子科技有限公司",
        "doc_no": "DYYY-JZ-2009-6821-02",
        "type": "医疗器械投标书",
        "chunks_count": 495,
        "tags": ["医疗器械", "政府采购", "投标文件"],
    },
    {
        "id": "medical_instrument_bid",
        "filename": "medical_instrument_bid.pdf",
        "title": "全自动五分类血液分析仪 — 医用器械投标书",
        "description": "医院设备招标项目投标书，含投标函、报价表、技术偏差表",
        "company": "*** 有限责任公司",
        "doc_no": "N/A",
        "type": "医用器械投标书",
        "chunks_count": 157,
        "tags": ["医用器械", "血液分析仪", "采购"],
    },
]


@app.get("/api/corpus")
async def list_corpus():
    """List real Chinese medical procurement documents available for demo."""
    return {"documents": CORPUS_META, "total": len(CORPUS_META)}


@app.get("/api/corpus/{filename}")
async def serve_corpus_pdf(filename: str):
    """Serve a real Chinese procurement PDF."""
    safe_name = Path(filename).name
    pdf_path = PDF_DOCS_DIR / safe_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {safe_name}")
    return FileResponse(str(pdf_path), media_type="application/pdf")


@app.get("/api/corpus/{filename}/chunks")
async def get_corpus_chunks(filename: str, page: int = 0, limit: int = 20):
    """Return Azure DI extracted chunks for a corpus document."""
    stem = Path(filename).stem
    from doc_parser import load_from_cache
    chunks = load_from_cache(stem)
    if chunks is None:
        raise HTTPException(status_code=404, detail="Not yet processed. POST /api/demo/process first.")
    start = page * limit
    return {
        "filename": filename,
        "total": len(chunks),
        "page": page,
        "chunks": chunks[start: start + limit],
    }


@app.get("/")
async def root():
    return {"service": "hk-prvet-demo-api", "docs": "/docs", "status": _status["state"]}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
