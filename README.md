# PreVet Intelligence — Backend

> FastAPI backend for the HK PreVet Intelligence Demo.
> Connects to [hk-prvet-demo](https://github.com/destiny520537work-lab/hk-prvet-demo) frontend.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi&logoColor=white)
![Azure](https://img.shields.io/badge/Azure_DI-1.0-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)

**Frontend repo:** [hk-prvet-demo](https://github.com/destiny520537work-lab/hk-prvet-demo)

---

## What It Does

Processes pharmaceutical licensing application documents for the HK Dept. of Health demo:

1. **Azure Document Intelligence** — parses PDFs, returns text chunks with real bounding box coordinates
2. **BM25 field extraction** — locates 23 known compliance fields in their source documents
3. **Knowledge Graph** — NetworkX graph over 7 entities (company, directors, legal cases, news events), finds risk paths
4. **REST API** — serves extracted data in the exact format the React frontend expects

---

## Quick Start

### Prerequisites

- Python 3.11+
- Azure Document Intelligence resource (for real PDF processing)
- Frontend running on `localhost:5173`

### Install

```bash
git clone https://github.com/destiny520537work-lab/hk-prvet-backend
cd hk-prvet-backend
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env:
# AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://YOUR_RESOURCE.cognitiveservices.azure.com/
# AZURE_DOCUMENT_INTELLIGENCE_KEY=your_key_here
# PDF_DOCS_PATH=../hk-prvet-demo/dist/docs
```

### Run

```bash
uvicorn main:app --reload --port 8000
# API docs → http://localhost:8000/docs
```

On startup, the backend loads cached Azure DI results from `cache/`. Processing runs once and never again unless `cache/` is cleared.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/demo/process` | Trigger Azure DI processing of 6 demo PDFs (async) |
| `GET` | `/api/demo/status` | Poll processing status (`idle` / `processing` / `ready`) |
| `GET` | `/api/demo/points` | 23 extracted data points with real bounding boxes |
| `GET` | `/api/demo/background` | Background check results (6 items + risk verdict) |
| `GET` | `/api/demo/kg` | KG graph data (nodes, edges, risk paths) |
| `GET` | `/api/pdf/{filename}` | Serve a demo PDF file |
| `GET` | `/api/corpus` | List real Chinese medical procurement documents |
| `GET` | `/api/corpus/{filename}` | Serve a corpus PDF |
| `GET` | `/api/corpus/{filename}/chunks` | Azure DI extracted chunks for a corpus doc |

Full interactive docs: `http://localhost:8000/docs`

---

## Architecture

```
main.py  (FastAPI)
├── doc_parser.py        Azure DI → [{text, page_idx, bbox[0-1000], type}]
│                        Caches results to cache/{stem}.json
│
├── bm25_index.py        BM25 full-text search
│                        find_best_bbox(query, fallback) → HighlightBox {x,y,w,h in %}
│
├── field_rules.py       23 field definitions
│                        {id, label, doc_filename, bm25_query, expected_value,
│                         source_type, fallback_box, [status_override, risk_note]}
│
├── kg_service.py        Knowledge Graph interface (NetworkX)
│   └── kg_data.py       Seed data: 7 nodes, 6 edges, 2 risk paths
│                        Interface abstracted → swap NetworkX for Neo4j later
│
└── cache/               Azure DI results (git-ignored)
    ├── business_registration_certificate.json
    ├── supplier_contract_sinopharm.json
    └── ...
```

### Coordinate system

Azure DI returns bounding boxes in `[x0, y0, x1, y1]` with values `[0, 1000]` (normalized to page dimensions).

The frontend `HighlightOverlay` component expects `{x, y, width, height}` as percentages `[0, 100]`.

Conversion in `bm25_index.py`:
```python
highlight_box = {
    "x":      bbox[0] / 10,
    "y":      bbox[1] / 10,
    "width":  (bbox[2] - bbox[0]) / 10,
    "height": (bbox[3] - bbox[1]) / 10,
}
```

### BM25 field location

For each of the 23 fields, the backend:
1. Searches the relevant document's BM25 index with `field_rules.bm25_query`
2. If score > 0.3 → uses that chunk's real Azure DI bbox
3. If score ≤ 0.3 → falls back to `field_rules.fallback_box` (pre-calibrated from Azure DI)

**Important:** BM25 queries must match the *exact text in the PDF*, not a conceptual description. For example, a contract that labels the start date as `"Agreement Date:"` requires query `"1 January 2024"`, not `"contract start date"`.

### Knowledge Graph

```
Nodes:  Company / Person / LegalCase / NewsEvent / Regulatory
Edges:  directorOf / involvedIn / relatedTo / hasRecord

Risk path query:
  nx.shortest_path(G, "company:medprime", high_risk_node)
  → returns path within 3 hops
```

KG interface is abstracted in `kg_service.py` — replacing NetworkX with Neo4j only requires changing the internal implementation, not the API.

---

## Files

```
hk-prvet-backend/
├── main.py           FastAPI app, all endpoints, startup logic
├── doc_parser.py     Azure DI integration (async, with cache)
├── bm25_index.py     BM25 index + bbox coordinate conversion
├── field_rules.py    23 field definitions for MedPrime case
├── kg_service.py     KG interface layer (NetworkX)
├── kg_data.py        KG seed data (nodes, edges, risk paths)
├── requirements.txt
├── .env.example
└── cache/            (git-ignored) Azure DI JSON results
```

---

## Known Limitations

- **BM25 is format-sensitive** — queries are calibrated to the 6 demo PDFs. Different document layouts will need updated queries. Production upgrade path: replace BM25 with LLM extraction (Claude API reads document text, returns field value + exact source text, then exact string match finds the bbox).
- **KG is pre-seeded** — the knowledge graph uses static seed data for the demo case. Production: connect to live Companies Registry / court records APIs.
- **Single-case demo** — no case management or multi-user support. One fixed applicant (MedPrime Healthcare Supplies Ltd.).

---

## License

MIT
