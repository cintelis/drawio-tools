"""Clearline design diagrams, built with drawgen's Python API.

Run:  uv run python examples/clearline/build.py [--renderer builtin|drawio|auto]

Writes examples/clearline/out/<name>.drawio.svg: editable images that render on
GitHub and reopen in draw.io. Regenerate from here when the architecture
changes; hand edits made in draw.io are overwritten on the next run.
"""
import argparse
import os
import sys

from drawgen import Diagram, check_xml
from drawgen.export import render, temp_drawio

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
RENDERER = "auto"
PROBLEMS = 0


def done(d: Diagram, name: str) -> None:
    global PROBLEMS
    xml = d.xml()
    report = check_xml(xml, path=name)
    PROBLEMS += len(report.errors)
    tmp = temp_drawio(xml)
    try:
        r = render(tmp, "svg", os.path.join(OUT, f"{name}.drawio.svg"), renderer=RENDERER)
    finally:
        os.remove(tmp)
    print(f"{name} -> {os.path.basename(r.path)} ({r.renderer}); "
          f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    for issue in report.issues:
        print(f"    {issue}")


# --------------------------------------------------------------------------- 01
def system_context():
    d = Diagram("01 · System context", 1440, 960,
                subtitle="Who uses Clearline and which external systems it depends on (C4 level 1).")
    actors = [
        ("merchant", "Cross-border seller", "Ops / founder of an SMB brand"),
        ("reviewer", "Compliance reviewer", "In-house or licensed broker partner"),
        ("agent", "AI agent", "Claude or other MCP client"),
        ("dev", "Developer", "3PL, marketplace or platform team"),
    ]
    core_y, core_h = 290, 380
    for i, (nid, lab, sub) in enumerate(actors):
        y = 305 + i * 92
        d.node(nid, lab, 50, y, 230, 70, "actor", sub)
    d.node("core", "Clearline platform", 580, core_y, 300, core_h, "service",
           "Classification\ntariff data\nlanded cost\naudit file\nrefund analysis")
    d.node("commerce", "Commerce platforms", 565, 130, 330, 80, "external",
           "Shopify · WooCommerce · BigCommerce · Amazon SP-API · CSV")
    gov = [("tariffs", "Tariff schedules", "USITC HTS · UK Trade Tariff API · EU TARIC", "Daily ingest"),
           ("rulings", "Classification rulings", "CBP CROSS · EU EBTI", "Weekly ingest"),
           ("notices", "Change notices", "Federal Register · CBP CSMS · WCO HS 2028", "Change watch")]
    for i, (nid, lab, sub, el) in enumerate(gov):
        y = 320 + i * 115
        d.node(nid, lab, 1110, y, 290, 80, "gov", sub)
        d.edge(nid, "core", el, "data", exit="left", entry=(1, (y + 40 - core_y) / core_h))
    labels = ["Classify catalogue, quote duties", "Review low-confidence items", "MCP tools",
              "REST API + webhooks"]
    for i, (nid, *_rest) in enumerate(actors):
        cy = 305 + i * 92 + 35
        d.edge(nid, "core", labels[i], exit="right", entry=(0, (cy - core_y) / core_h))
    d.node("llm", "LLM provider", 330, 760, 220, 76, "external", "Anthropic Claude API")
    d.node("carriers", "Carriers & 3PLs", 620, 760, 220, 76, "external", "Commercial invoice, HS + origin")
    d.node("broker", "Licensed customs broker", 910, 760, 240, 76, "external", "Files CAPE / protests in CBP ACE")
    d.edge("commerce", "core", "Catalogue sync, write back HS + origin", both=True,
           exit="bottom", entry="top")
    d.edge("core", "llm", "Extraction + GRI reasoning", "ai", exit=(0.2, 1), entry="top")
    d.edge("core", "carriers", "Invoice data", "sync", exit=(0.5, 1), entry="top")
    d.edge("core", "broker", "Declaration files", "weak", exit=(0.8, 1), entry="top")
    d.legend(40, 700, ["actor", "service", "external", "gov"], ["sync", "data", "ai", "weak"])
    done(d, "01-system-context")


# --------------------------------------------------------------------------- 02
def containers():
    d = Diagram("02 · Container architecture", 1720, 1060,
                subtitle="Deployable units and their main interactions (C4 level 2). "
                         "Internal service calls go through the Core API module boundary.")
    d.zone("zc", "Clients", 40, 100, 240, 620, "teal")
    for i, (nid, lab, sub) in enumerate([
        ("web", "Web dashboard", "Next.js"),
        ("shopapp", "Shopify embedded app", "React Router + Polaris"),
        ("mcpc", "MCP clients", "Claude Desktop / Code"),
        ("apic", "API consumers", "3PLs, platforms"),
    ]):
        d.node(nid, lab, 60, 160 + i * 135, 200, 76, "ui", sub, zone="zc")

    d.zone("ze", "Edge", 310, 100, 220, 620, "grey")
    d.node("gw", "API edge", 330, 250, 180, 90, "service", "CloudFront + WAF + ALB", zone="ze")
    d.node("auth", "Identity", 330, 460, 180, 80, "external", "OIDC (WorkOS) + API keys", zone="ze")

    d.zone("za", "Application services (Python 3.12 · FastAPI unless noted)", 560, 100, 560, 620, "green")
    svc = [
        ("api", "Core API", "REST, auth, tenancy, billing hooks", 590, 150),
        ("mcp", "MCP server", "TypeScript · streamable HTTP", 860, 150),
        ("lc", "Landed cost service", "Duty + tax rules engine", 590, 265),
        ("cls", "Classification service", "Pipeline orchestration", 860, 265),
        ("tds", "Tariff data service", "Versioned lookups", 590, 380),
        ("intg", "Integration service", "Connectors, webhooks", 860, 380),
        ("rfd", "Refund analyser", "ACE report parsing, CAPE CSV", 590, 495),
        ("ntf", "Notification service", "Alerts, digests", 860, 495),
    ]
    for nid, lab, sub, x, y in svc:
        d.node(nid, lab, x, y, 230, 80, "service", sub, zone="za")
    d.node("rules", "Rules packs", 725, 615, 230, 70, "note",
           "Country duty/tax rules as versioned code + tests", zone="za")

    d.zone("zw", "Async & AI", 1150, 100, 260, 620, "purple")
    d.node("tmp", "Temporal workers", 1170, 150, 220, 80, "worker",
           "Ingestion · batch classify · monitoring", zone="zw")
    d.node("llmgw", "LLM gateway", 1170, 300, 220, 80, "ai",
           "Model router · prompt cache · tracing", zone="zw")
    d.node("emb", "Embedding service", 1170, 450, 220, 80, "ai",
           "Nomenclature + rulings vectors", zone="zw")
    d.node("evalh", "Eval harness", 1170, 600, 220, 80, "ai",
           "Gold sets · regression gate", zone="zw")

    d.zone("zd", "Data", 560, 760, 850, 190, "blue")
    d.node("pg", "PostgreSQL 16", 590, 810, 180, 96, "datastore", "pgvector · RLS · bitemporal", zone="zd")
    d.node("redis", "Redis", 800, 810, 170, 96, "datastore", "Cache · rate limits", zone="zd")
    d.node("s3", "S3", 1000, 810, 170, 96, "datastore", "Raw snapshots · evidence", zone="zd")
    d.node("bus", "Event bus", 1200, 815, 180, 86, "queue", "EventBridge + SQS", zone="zd")

    ext = [("gov", "Government sources", "HTS · TARIC · UK · rulings", 150), ("anth", "Anthropic API", "Claude models", 300),
           ("plat", "Commerce platforms", "Shopify · Amazon · Woo", 450), ("stripe", "Stripe", "Subscriptions + usage", 600)]
    for nid, lab, sub, y in ext:
        d.node(nid, lab, 1460, y, 220, 80, "external", sub)

    for c in ["web", "shopapp", "mcpc", "apic"]:
        d.edge(c, "gw", "", entry="left")
    d.edge("gw", "api", "HTTPS", exit="right", entry="left")
    d.edge("gw", "auth", "Verify", "weak", exit="bottom", entry="top")
    d.edge("mcp", "api", "REST", exit="left", entry="right")  # the 40px gap fits one short word
    # Out of the lower right, down the gap between the rows and into the top of
    # Classification: the straight route ran through the MCP server box.
    d.edge("api", "cls", "", exit=(1, 0.75), entry="top", points=[(840, 210), (840, 247), (975, 247)])
    d.edge("api", "lc", "", exit="bottom", entry="top")
    d.edge("cls", "llmgw", "Prompts", "ai", exit="right", entry="left")
    d.edge("llmgw", "anth", "", "ai", exit="right", entry="left")
    d.edge("tmp", "gov", "Fetch", "data", exit="right", entry="left")
    d.edge("intg", "plat", "Sync", "sync", exit="right", entry="left",
           points=[(1435, 420), (1435, 490)])
    d.edge("za", "pg", "SQL", "data", exit="bottom", entry="top")
    d.edge("zw", "bus", "Events", "async", exit="bottom", entry="top")
    d.legend(40, 760, ["ui", "service", "worker", "ai", "datastore", "queue", "external"],
             ["sync", "async", "data", "ai"])
    done(d, "02-container-architecture")


# --------------------------------------------------------------------------- 03
def classification_pipeline():
    d = Diagram("03 · Classification pipeline", 1600, 980,
                subtitle="From a product record to a defensible, destination-specific code. "
                         "The model may only choose among retrieved, valid candidates.")
    d.node("in", "Product record", 40, 150, 160, 64, "terminal", "title, text, images, attributes")
    d.node("norm", "1 · Normalise & enrich", 240, 150, 190, 64, "step", "language, units, dedupe")
    d.node("ext", "2 · Extract attributes", 470, 150, 190, 64, "ai", "material %, function, construction")
    d.node("suff", "3 · Enough to\nclassify?", 700, 128, 170, 108, "decision")
    d.node("ask", "Ask clarifying question", 930, 150, 210, 64, "ui", "merchant answers in app / API")

    d.node("ret", "4 · Hybrid retrieval", 200, 400, 210, 72, "service", "lexical + vector, chapter to subheading")
    d.node("gri", "5 · GRI reasoning", 470, 400, 190, 72, "ai", "candidates only, cites notes")
    d.node("val", "6 · Validate", 700, 400, 170, 72, "service", "exists, declarable, trap rules")
    d.node("cal", "7 · Calibrate", 910, 400, 170, 72, "service", "self-consistency + margin")
    d.node("band", "Confidence\nband", 1120, 380, 150, 112, "decision")

    d.node("auto", "Auto-approve", 1340, 270, 200, 64, "step", "high band, tenant opt-in")
    d.node("conf", "Merchant confirms", 1340, 404, 200, 64, "ui", "medium band")
    d.node("rev", "Expert review queue", 1340, 538, 200, 64, "ui", "low band or restricted goods")

    d.node("nat", "8 · National extension", 1120, 700, 210, 72, "service", "HS6 → HTS10 / CN8 / UK10")
    d.node("aud", "Decision + audit file", 870, 690, 200, 92, "datastore", "evidence, versions, reviewer")
    d.node("out", "Code per destination", 600, 708, 210, 64, "terminal", "with rationale + confidence")

    d.node("k1", "Nomenclature + notes", 20, 590, 180, 84, "datastore", "HS 2022 / 2028 tables")
    d.node("k2", "Rulings index", 220, 590, 160, 84, "datastore", "CROSS · EBTI")
    d.node("k3", "Tenant memory", 400, 590, 160, 84, "datastore", "approved SKUs")

    d.edge("in", "norm")
    d.edge("norm", "ext")
    d.edge("ext", "suff")
    d.edge("suff", "ask", "No")
    d.edge("ask", "ext", "Answer", "weak", exit="top", entry="top", points=[(1035, 110), (565, 110)])
    d.edge("suff", "ret", "Yes", exit="bottom", entry="top", points=[(785, 320), (305, 320)])
    d.edge("ret", "gri", "Top-k")
    d.edge("gri", "val")
    d.edge("val", "cal")
    d.edge("cal", "band")
    d.edge("band", "auto", "High", exit="top", entry="left", points=[(1195, 302)])
    d.edge("band", "conf", "Medium", exit="right", entry="left")
    d.edge("band", "rev", "Low", exit="bottom", entry="left", points=[(1195, 570)])
    d.edge("auto", "nat", "", exit="right", entry="right", points=[(1570, 302), (1570, 736)])
    d.edge("conf", "nat", "", exit="right", entry="right", points=[(1570, 436), (1570, 736)])
    d.edge("rev", "nat", "", exit="right", entry="right", points=[(1570, 570), (1570, 736)])
    d.edge("nat", "aud")
    d.edge("aud", "out")
    d.edge("k1", "ret", "", "data", exit="top", entry=(0.2, 1))
    d.edge("k2", "ret", "", "data", exit="top", entry=(0.55, 1))
    d.edge("k3", "ret", "", "data", exit="top", entry=(0.9, 1))
    d.legend(40, 720, ["terminal", "step", "ai", "service", "ui", "datastore"], ["sync", "data", "weak"])
    done(d, "03-classification-pipeline")


# --------------------------------------------------------------------------- 04
def tariff_platform():
    d = Diagram("04 · Tariff data platform", 1680, 860,
                subtitle="Every source is fetched, snapshotted immutably, parsed into one bitemporal model, "
                         "diffed, and turned into SKU-level alerts.")
    srcs = [
        ("s1", "USITC HTS", "REST/JSON per release"),
        ("s2", "Federal Register · CSMS", "Chapter 99 changes"),
        ("s3", "UK Trade Tariff API", "daily, OAuth keys"),
        ("s4", "EU TARIC", "XML / Excel extracts"),
        ("s5", "CBP CROSS", "rulings"),
        ("s6", "EU EBTI", "binding rulings"),
        ("s7", "WCO correlation", "HS 2022 → 2028"),
        ("s8", "ECB reference rates", "FX daily"),
    ]
    for i, (nid, lab, sub) in enumerate(srcs):
        d.node(nid, lab, 40, 110 + i * 82, 230, 62, "gov", sub)
    d.node("sched", "Fetch scheduler", 330, 360, 190, 84, "worker", "Temporal cron, retries, ETags")
    d.node("raw", "Raw snapshot store", 580, 180, 210, 96, "datastore", "S3 Object Lock, SHA-256")
    d.node("parse", "Source parsers", 580, 360, 210, 84, "worker", "one adapter per source")
    d.node("hum", "Measure authoring", 570, 520, 240, 84, "ui", "analyst encodes Ch.99 notes\n2-person review")
    d.node("canon", "Canonical tariff store", 910, 352, 230, 100, "datastore", "bitemporal: valid + recorded time")
    d.node("idx", "Index builder", 910, 180, 230, 84, "worker", "chunks notes + rulings")
    d.node("vec", "Retrieval indexes", 1210, 172, 200, 100, "datastore", "pgvector + tsvector")
    d.node("diff", "Diff engine", 1210, 360, 200, 84, "service", "release vs release")
    d.node("imp", "Impact analysis", 1210, 520, 210, 84, "service", "which SKUs, which tenants, $ effect")
    d.node("cons", "Consumers", 1480, 360, 170, 84, "service", "classification, landed cost")
    d.node("alert", "Alerts", 1480, 520, 170, 84, "service", "rules + digests")
    d.node("chan", "Email · webhooks · app", 1480, 680, 170, 70, "external")

    for nid, *_ in srcs:
        d.edge(nid, "sched", "", "data", exit="right", entry="left")
    d.edge("sched", "raw", "Store as fetched", "data", exit="top", entry="left", points=[(425, 228)])
    d.edge("raw", "parse", "", "data", exit="bottom", entry="top")
    d.edge("parse", "canon", "Upsert new version", "data")
    d.edge("hum", "canon", "Approved measures", "sync", exit="right", entry="bottom", points=[(1025, 562)])
    d.edge("canon", "idx", "", "data", exit="top", entry="bottom")
    d.edge("idx", "vec", "", "data")
    d.edge("canon", "diff", "", "data")
    d.edge("diff", "cons", "Cache bust", "async")
    d.edge("diff", "imp", "Changed lines", "async", exit="bottom", entry="top")
    d.edge("imp", "alert", "")
    d.edge("alert", "chan", "", "async", exit="bottom", entry="top")
    d.legend(330, 620, ["gov", "worker", "datastore", "service", "ui"], ["data", "async", "sync"])
    done(d, "04-tariff-data-platform")


# --------------------------------------------------------------------------- 05
def landed_cost():
    d = Diagram("05 · Landed cost calculation", 1440, 1180,
                subtitle="Deterministic rules engine. The LLM never computes duty; it only supplies the code upstream.")
    steps = [
        ("q", "Quote request", "lines, origin, destination, value, incoterm, channel", "terminal"),
        ("c1", "Resolve codes", "approved destination code per SKU", "step"),
        ("c2", "Select regime", "low-value rules, postal vs commercial, B2C vs B2B", "decision"),
        ("c3", "Customs value", "US: FOB basis · EU/UK: CIF basis", "step"),
        ("c4", "Base duty", "MFN or preference (flagged, never assumed)", "step"),
        ("c5", "Additional duties", "US Ch.99 stack · EU €3 per HS6 line ≤ €150", "step"),
        ("c6", "Taxes", "VAT / GST on (value + duty), IOSS / LVG", "step"),
        ("c7", "Fees", "MPF, carrier disbursement, handling fees", "step"),
        ("c8", "FX & rounding", "ECB / Fed rates, per-country rounding", "step"),
        ("r", "Quote response", "line breakdown + rule citations + data version", "terminal"),
    ]
    y = 100
    for nid, lab, sub, kind in steps:
        h = 110 if kind == "decision" else 70
        w = 260 if kind != "decision" else 340
        d.node(nid, lab, 550 - w / 2, y, w, h, kind, sub)
        y += h + 26
    for a, b in zip([s[0] for s in steps][:-1], [s[0] for s in steps][1:]):
        d.edge(a, b, "", exit="bottom", entry="top")

    notes = [
        ("n1", "United States", "De minimis suspended since Aug 2025.\nSection 122 surcharge expired 24 Jul 2026.\n"
         "Section 301 forced-labour tariff 10% / 12.5% from 24 Jul 2026.\nSection 232 metals on full value since 6 Apr 2026.\n"
         "Postal: MFN + 232 + 301 apply from 24 Jul 2026.", "c5", 330),
        ("n2", "European Union", "€150 relief abolished 1 Jul 2026.\n€3 flat duty per HS6 line on low-value B2C.\n"
         "Import VAT unchanged (IOSS for ≤ €150).\nHandling fee planned from Nov 2026.", "c5", 520),
        ("n3", "United Kingdom", "£135 relief continues to at least 31 Dec 2026.\nRemoval by Oct 2028 at the latest.\n"
         "VAT at point of sale ≤ £135 since 2021.", "c6", 700),
        ("n4", "Every rule is a versioned pack", "Effective dates, source citation and\nunit tests per country. "
         "Unknown regime =\nreturn 'needs review', never a guess.", "c2", 160),
    ]
    for nid, lab, body, anchor, ny in notes:
        d.node(nid, lab, 860, ny, 400, 150 if nid != "n4" else 110, "note", sub=body)
        d.edge(nid, anchor, "", "weak", exit="left", entry="right")
    d.node("src", "Canonical tariff store", 60, 470, 220, 96, "datastore", "measures valid on ship date")
    d.edge("src", "c4", "", "data", exit="right", entry="left")
    d.edge("src", "c5", "", "data", exit="right", entry="left")
    d.legend(60, 640, ["terminal", "step", "decision", "datastore", "note"], ["sync", "data", "weak"])
    done(d, "05-landed-cost-flow")


# --------------------------------------------------------------------------- 06
def erd():
    d = Diagram("06 · Core data model", 1760, 1180,
                subtitle="Tenant-scoped tables use Postgres row-level security on tenant_id. "
                         "Tariff tables are global and bitemporal.")
    d.zone("zt", "Tenant data (RLS)", 30, 90, 1110, 1060, "green")
    d.zone("zg", "Global reference data (bitemporal)", 1170, 90, 560, 1060, "blue")
    E = d.entity
    E("tenant", "tenant", ["PK id uuid", "name", "plan", "region", "auto_approve_band", "created_at"], 60, 140, zone="zt")
    E("product", "product", ["PK id uuid", "FK tenant_id", "external_ref", "source", "title", "description",
                             "attributes jsonb", "origin_country", "content_hash", "updated_at"], 330, 140, zone="zt")
    E("creq", "classification_request", ["PK id uuid", "FK tenant_id", "FK product_id", "destinations text[]",
                                         "status", "pipeline_version", "created_at"], 600, 140, w=250, zone="zt")
    E("dec", "classification_decision", ["PK id uuid", "FK request_id", "hs6", "confidence", "band",
                                         "rationale jsonb", "model_trace_id", "decided_by", "state", "decided_at"],
      600, 430, w=250, zone="zt")
    E("ev", "decision_evidence", ["PK id uuid", "FK decision_id", "kind (note|ruling|sku)", "ref",
                                  "excerpt_hash", "weight"], 880, 140, w=230, zone="zt")
    E("nat", "destination_code", ["PK id uuid", "FK decision_id", "country", "code", "FK nomenclature_id",
                                  "valid_from", "valid_to"], 880, 480, w=230, zone="zt")
    E("q", "quote", ["PK id uuid", "FK tenant_id", "origin", "destination", "incoterm", "channel",
                     "currency", "data_version", "total"], 60, 420, zone="zt")
    E("ql", "quote_line", ["PK id uuid", "FK quote_id", "FK product_id", "code", "customs_value",
                           "duties jsonb", "taxes jsonb", "fees jsonb"], 330, 470, zone="zt")
    E("alert", "alert", ["PK id uuid", "FK tenant_id", "FK product_id", "FK change_id", "severity",
                         "delta_estimate", "state"], 60, 740, zone="zt")
    E("rc", "refund_case", ["PK id uuid", "FK tenant_id", "ior_number_hash", "status",
                            "est_refund", "deadline_at"], 330, 780, zone="zt")
    E("el", "entry_line", ["PK id uuid", "FK refund_case_id", "entry_no", "line_no", "hts", "ch99_codes text[]",
                           "duty_paid", "liquidation_status", "liquidation_date", "pathway"], 600, 740, w=250, zone="zt")
    E("ae", "audit_event", ["PK id bigserial", "FK tenant_id", "actor", "action", "subject",
                            "payload_hash", "prev_hash", "at"], 880, 740, w=230, zone="zt")

    E("rel", "tariff_release", ["PK id uuid", "country", "edition", "source_url", "snapshot_sha256",
                                "published_at", "ingested_at"], 1200, 140, w=240, zone="zg")
    E("nom", "nomenclature_node", ["PK id uuid", "FK release_id", "country", "code", "level",
                                   "description", "declarable", "valid_from", "valid_to", "recorded_at"],
      1470, 140, w=240, zone="zg")
    E("mea", "measure", ["PK id uuid", "FK nomenclature_id", "type (mfn|pref|ch99|vat|flat)",
                         "origin_scope", "rate_expr", "legal_ref", "valid_from", "valid_to", "recorded_at"],
      1200, 440, w=240, zone="zg")
    E("rul", "ruling", ["PK id text", "authority (CBP|EBTI)", "code", "issued_at", "status",
                        "summary", "embedding vector"], 1470, 470, w=240, zone="zg")
    E("chg", "tariff_change", ["PK id uuid", "FK release_id", "code", "change_type", "before jsonb",
                               "after jsonb", "effective_at"], 1200, 760, w=240, zone="zg")
    E("cor", "hs_correlation", ["PK id uuid", "from_edition", "from_code", "to_edition", "to_code",
                                "relation (1:1|1:n|n:1)"], 1470, 790, w=240, zone="zg")

    rel = [("product", "tenant"), ("creq", "product"), ("dec", "creq"), ("ev", "dec"), ("nat", "dec"),
           ("q", "tenant"), ("ql", "q"), ("alert", "chg"), ("el", "rc"), ("nom", "rel"), ("mea", "nom"),
           ("chg", "rel")]
    rel.remove(("alert", "chg"))
    for a, b in rel:
        if (a, b) == ("ev", "dec"):
            d.edge(a, b, "", "weak", arrow="ERmandOne", exit="bottom", entry=(1, 0.2),
                   points=[(995, 330), (866, 330)])
            continue
        if (a, b) == ("nat", "dec"):
            d.edge(a, b, "", "weak", arrow="ERmandOne", exit="left", entry=(1, 0.75))
            continue
        if (a, b) == ("chg", "rel"):
            d.edge(a, b, "", "weak", arrow="ERmandOne", exit="left", entry="left",
                   points=[(1186, 670), (1186, 250)])
            continue
        if (a, b) == ("mea", "nom"):
            d.edge(a, b, "", "weak", arrow="ERmandOne", exit="top", entry="bottom",
                   points=[(1320, 410), (1590, 410)])
            continue
        d.edge(a, b, "", "weak", arrow="ERmandOne")
    d.node("xref", "Cross-zone references (not drawn)", 1200, 1000, 510, 110, "note",
           sub="destination_code.nomenclature_id → nomenclature_node.id\n"
               "alert.change_id → tariff_change.id\n"
               "decision_evidence.ref → ruling.id when kind = ruling")
    done(d, "06-data-model")


# --------------------------------------------------------------------------- 07
def refund_workflow():
    d = Diagram("07 · US duty refund recovery workflow", 1760, 960,
                subtitle="Clearline analyses and prepares; the importer of record or a licensed broker files. "
                         "Applies to IEEPA duties now and Section 122 duties if courts extend relief.")
    lanes = [("l1", "Importer of record (merchant)", "teal"), ("l2", "Clearline", "green"),
             ("l3", "Licensed customs broker", "amber"), ("l4", "CBP ACE", "grey")]
    for i, (lid, lab, col) in enumerate(lanes):
        d.zone(lid, lab, 30, 100 + i * 205, 1700, 190, col)

    d.node("u1", "Export ACE reports", 70, 160, 200, 70, "ui", "entry summaries, liquidation status", zone="l1")
    d.node("u2", "Confirm ACE portal + ACH", 700, 160, 240, 70, "ui", "prerequisite before anything is filed", zone="l1")
    d.node("u3", "Refund received", 1290, 160, 200, 70, "terminal", "ACH, typically 60-90 days", zone="l1")

    d.node("c1", "Parse & normalise", 70, 365, 190, 70, "service", "entries, lines, Ch.99 codes", zone="l2")
    d.node("c2", "Detect refundable duty", 290, 365, 200, 70, "service", "IEEPA / s122 Chapter 99 lines", zone="l2")
    d.node("c3", "Pathway?", 530, 345, 150, 110, "decision", zone="l2")
    d.node("c4", "CAPE declaration CSV", 740, 318, 220, 64, "service", "unliquidated or ≤ 80 days post", zone="l2")
    d.node("c5", "Protest pack", 740, 410, 220, 64, "service", "liquidated, within 180 days", zone="l2")
    d.node("c6", "Deadline tracker", 1020, 365, 200, 70, "worker", "per-entry clocks + alerts", zone="l2")
    d.node("c7", "Reconcile & invoice", 1500, 365, 200, 70, "service", "success fee on recovered $", zone="l2")
    d.node("c8", "Excluded or watchlist", 300, 452, 170, 36, "note", zone="l2")

    d.node("b1", "Review & file", 1010, 570, 220, 70, "step", "or IOR files directly", zone="l3")
    d.node("g1", "Validate & reliquidate", 1010, 775, 220, 70, "step", "removes IEEPA Ch.99 lines", zone="l4")
    d.node("g2", "Refund issued", 1290, 775, 200, 70, "step", "consolidated by IOR / 4811 party", zone="l4")

    d.edge("u1", "c1", "Upload CSV", exit="bottom", entry="top")
    d.edge("c1", "c2")
    d.edge("c2", "c3")
    d.edge("c3", "c4", "CAPE", exit="right", entry="left")
    d.edge("c3", "c5", "Protest", exit="right", entry="left")
    d.edge("c3", "c8", "Excluded", "weak", exit="bottom", entry="right")
    d.edge("c4", "c6", "", entry=(0, 0.3))
    d.edge("c5", "c6", "", entry=(0, 0.7))
    d.edge("c6", "b1", "Ready to file", exit="bottom", entry="top")
    d.edge("b1", "g1", "Submit in ACE", exit="bottom", entry="top")
    d.edge("g1", "g2")
    d.edge("g2", "u3", "ACH refund", exit="top", entry="bottom")
    d.edge("u3", "c7", "Merchant confirms", "weak", exit="right", entry="top")
    done(d, "07-refund-recovery-workflow")


# --------------------------------------------------------------------------- 08
def deployment():
    d = Diagram("08 · Deployment (AWS)", 1600, 960,
                subtitle="Single primary region at launch; EU region added when EU tenants need data residency.")
    d.zone("reg", "AWS us-east-1 (primary)", 300, 100, 1000, 720, "blue")
    d.node("users", "Users & agents", 40, 160, 200, 70, "actor", "browser, Shopify, MCP")
    d.node("r53", "Route 53 + CloudFront", 340, 160, 220, 76, "service", "WAF, TLS 1.3", zone="reg")
    d.node("alb", "Application Load Balancer", 340, 300, 220, 76, "service", zone="reg")
    d.zone("ecs", "ECS Fargate (private subnets, 3 AZ)", 600, 150, 420, 400, "green")
    for i, (nid, lab, sub) in enumerate([("t_api", "api", "FastAPI · 2-20 tasks"),
                                         ("t_mcp", "mcp", "TypeScript · 2-6 tasks"),
                                         ("t_web", "web", "Next.js · 2-6 tasks"),
                                         ("t_wrk", "workers", "Temporal · 2-30 tasks")]):
        d.node(nid, lab, 630 + (i % 2) * 190, 200 + (i // 2) * 150, 170, 90, "service", sub, zone="ecs")
    d.node("rds", "RDS PostgreSQL 16", 340, 600, 220, 100, "datastore", "Multi-AZ, PITR 35 days", zone="reg")
    d.node("ec", "ElastiCache Redis", 600, 610, 190, 90, "datastore", zone="reg")
    d.node("s3", "S3", 830, 610, 190, 90, "datastore", "Object Lock for snapshots", zone="reg")
    d.node("sec", "Secrets Manager + KMS", 1060, 170, 210, 76, "service", "CMK per environment", zone="reg")
    d.node("obs", "Observability", 1060, 320, 210, 90, "service", "OTel → CloudWatch, Langfuse", zone="reg")
    d.node("eb", "EventBridge + SQS", 1060, 610, 210, 90, "queue", zone="reg")
    d.node("tc", "Temporal Cloud", 1350, 232, 210, 76, "external", "namespaces per env")
    d.node("anth", "Anthropic API", 1350, 452, 210, 76, "external")
    d.node("gh", "GitHub Actions", 40, 450, 200, 76, "external", "OIDC to AWS, ECR push")
    d.node("eu", "AWS eu-west-1", 1350, 620, 210, 90, "external", "phase 2: EU tenant data")

    d.edge("users", "r53", "HTTPS")
    d.edge("r53", "alb", "", exit="bottom", entry="top")
    d.edge("alb", "ecs", "", exit="right", entry="left")
    d.edge("ecs", "rds", "SQL", "data", exit="bottom", entry="top", points=[(810, 575), (450, 575)])
    d.edge("ecs", "ec", "", "data", exit="bottom", entry="top")
    d.edge("ecs", "s3", "", "data", exit="bottom", entry="top", points=[(810, 575), (925, 575)])
    d.edge("ecs", "tc", "gRPC", "async", exit=(1, 0.3), entry="left")
    d.edge("ecs", "anth", "Model calls", "ai", exit=(1, 0.85), entry="left")
    d.edge("gh", "ecs", "Deploy", "weak", exit="right", entry="bottom", points=[(270, 488), (270, 560), (700, 560)])
    d.legend(40, 600, ["actor", "service", "datastore", "queue", "external"], ["sync", "data", "async", "ai"])
    done(d, "08-deployment-aws")


# --------------------------------------------------------------------------- 09
def shopify_sequence():
    d = Diagram("09 · Shopify integration sequence", 1600, 1080,
                subtitle="Initial catalogue sync, review, write-back and change-driven reclassification.")
    lifelines = [("m", "Merchant"), ("s", "Shopify"), ("i", "Integration service"),
                 ("c", "Classification"), ("n", "Notification")]
    xs = [160, 460, 760, 1060, 1360]
    for (lid, lab), x in zip(lifelines, xs):
        kind = "actor" if lid == "m" else ("external" if lid == "s" else "service")
        d.node(f"h_{lid}", lab, x - 110, 100, 220, 56, kind)
        d.add_vertex(f"line_{lid}", "", "line;strokeWidth=1.5;strokeColor=#9CA3AF;dashed=1;dashPattern=4 4;direction=south;drawgenRole=decor;"
               "html=1;", x - 1, 156, 2, 880)
    msgs = [
        ("m", "s", "1 · Install app (OAuth, scopes)"),
        ("s", "i", "2 · Access token + shop webhook registration"),
        ("i", "s", "3 · Bulk operation: products + inventory items"),
        ("s", "i", "4 · JSONL result URL"),
        ("i", "c", "5 · Batch classify (Temporal, idempotent per hash)"),
        ("c", "i", "6 · Decisions: auto / confirm / review"),
        ("i", "m", "7 · Review queue in embedded app"),
        ("m", "i", "8 · Approve or correct"),
        ("i", "s", "9 · inventoryItemUpdate: HS, origin, country codes"),
        ("s", "i", "10 · Webhook products/update"),
        ("i", "c", "11 · Reclassify only if material fields changed"),
        ("c", "n", "12 · Tariff change hits SKU"),
        ("n", "m", "13 · Alert with $ impact"),
    ]
    xmap = dict(zip([l[0] for l in lifelines], xs))
    for i, (a, b, lab) in enumerate(msgs):
        y = 200 + i * 64
        d.add_vertex(f"pa{i}", "", "points=[];fillColor=none;strokeColor=none;drawgenRole=decor;", xmap[a], y, 1, 1)
        d.add_vertex(f"pb{i}", "", "points=[];fillColor=none;strokeColor=none;drawgenRole=decor;", xmap[b], y, 1, 1)
        style = "async" if lab.startswith(("10", "12", "13")) else "sync"
        d.edge(f"pa{i}", f"pb{i}", lab, style, curved=True)
    done(d, "09-shopify-integration-sequence")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--renderer", default="auto", choices=["auto", "drawio", "builtin"])
    RENDERER = ap.parse_args().renderer
    os.makedirs(OUT, exist_ok=True)
    for fn in [system_context, containers, classification_pipeline, tariff_platform, landed_cost,
               erd, refund_workflow, deployment, shopify_sequence]:
        fn()
    sys.exit(1 if PROBLEMS else 0)
