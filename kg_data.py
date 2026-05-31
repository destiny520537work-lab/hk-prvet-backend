"""
KG seed data for the MedPrime demo case.
Loaded once at startup into kg_service.py.

To migrate to Neo4j later: keep this file as seed data,
change kg_service.py to write to Neo4j instead of NetworkX.
"""

KG_NODES = [
    {
        "id": "company:medprime",
        "type": "Company",
        "label": "MedPrime Healthcare",
        "sublabel": "醫泰醫療用品有限公司",
        "risk": "high",
        "properties": {
            "reg_no": "68423917",
            "address": "Unit 7, 15/F, Kowloon Bay Industrial Ctr",
            "licence_type": "Pharmaceutical Wholesale Dealer",
            "status": "under_review",
            "dimension_id": "business",
        },
    },
    {
        "id": "person:raymond_luk",
        "type": "Person",
        "label": "Raymond Luk Wai-man",
        "sublabel": "陸偉文",
        "risk": "medium",
        "properties": {"role": "Director", "id_suffix": "***251X", "dimension_id": "connected"},
    },
    {
        "id": "company:eastway",
        "type": "Company",
        "label": "Eastway Medical Supplies",
        "sublabel": "已吊銷牌照",
        "risk": "high",
        "properties": {
            "status": "licence_revoked",
            "revoked_date": "2023-11",
            "notes": "Failed annual compliance review",
            "dimension_id": "connected",
        },
    },
    {
        "id": "company:pacific_pharma",
        "type": "Company",
        "label": "Pacific Pharma Trading",
        "sublabel": "自願清盤",
        "risk": "medium",
        "properties": {"status": "voluntary_liquidation", "date": "2024-03"},
    },
    {
        "id": "case:dccj3847",
        "type": "LegalCase",
        "label": "DCCJ 3847/2022",
        "sublabel": "HKD 3.42M 貨款追討",
        "risk": "high",
        "properties": {
            "court": "HK District Court",
            "date": "2022-07-14",
            "plaintiff": "Bright Star Pharma Ltd",
            "amount_hkd": 3420000,
            "result": "plaintiff_won",
            "dimension_id": "judicial",
        },
    },
    {
        "id": "news:hkdoh_raid_2023",
        "type": "NewsEvent",
        "label": "DOH Raid Apr 2023",
        "sublabel": "未註冊藥物調查",
        "risk": "high",
        "properties": {
            "date": "2023-04",
            "source": "HK Health News Portal",
            "category": "regulatory_action",
            "dimension_id": "media",
        },
    },
    {
        "id": "regulatory:annual_return_late",
        "type": "Regulatory",
        "label": "Annual Return Late (2024)",
        "sublabel": "逾期 47 天",
        "risk": "review",
        "properties": {"delay_days": 47, "fine_hkd": 4800, "date": "2024-07-30", "dimension_id": "business"},
    },
]

KG_EDGES = [
    {
        "source": "person:raymond_luk",
        "target": "company:medprime",
        "type": "directorOf",
        "label": "董事",
    },
    {
        "source": "person:raymond_luk",
        "target": "company:eastway",
        "type": "directorOf",
        "label": "董事（已吊銷）",
        "note": "關聯公司牌照於 2023-11 被撤銷",
    },
    {
        "source": "person:raymond_luk",
        "target": "company:pacific_pharma",
        "type": "directorOf",
        "label": "董事（清盤）",
    },
    {
        "source": "company:medprime",
        "target": "case:dccj3847",
        "type": "involvedIn",
        "label": "被告",
    },
    {
        "source": "company:medprime",
        "target": "news:hkdoh_raid_2023",
        "type": "relatedTo",
        "label": "業務高度重疊",
        "confidence": 0.78,
    },
    {
        "source": "company:medprime",
        "target": "regulatory:annual_return_late",
        "type": "hasRecord",
        "label": "合規記錄",
    },
]

KG_RISK_PATHS = [
    {
        "description": "申请人董事 Raymond Luk 同时担任已吊销牌照公司 Eastway Medical Supplies 的董事，该公司于 2023-11 因未通过年度合规审查被吊销牌照",
        "path": ["company:medprime", "person:raymond_luk", "company:eastway"],
        "risk_level": "high",
        "why_risky": "董事关联吊销公司，合规文化存疑",
    },
    {
        "description": "申请人在 2022 年被供应商追讨 HKD 3.42M 货款，法院判申请人败诉",
        "path": ["company:medprime", "case:dccj3847"],
        "risk_level": "high",
        "why_risky": "财务诚信及合同履行存在历史问题",
    },
]
