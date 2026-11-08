#!/usr/bin/env python3
"""Build the final assignment report and enforce its page limit."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#14213D")
BLUE = colors.HexColor("#1F6FEB")
CYAN = colors.HexColor("#0E7490")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#526173")
PALE = colors.HexColor("#EEF4FB")
PALE_CYAN = colors.HexColor("#E8F7FA")
PALE_AMBER = colors.HexColor("#FFF6E5")
LINE = colors.HexColor("#CBD5E1")
WHITE = colors.white


def register_fonts() -> tuple[str, str, str]:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ),
    ]
    for regular, bold, italic in candidates:
        if all(Path(path).exists() for path in (regular, bold, italic)):
            pdfmetrics.registerFont(TTFont("ReportRegular", regular))
            pdfmetrics.registerFont(TTFont("ReportBold", bold))
            pdfmetrics.registerFont(TTFont("ReportItalic", italic))
            return "ReportRegular", "ReportBold", "ReportItalic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


REGULAR, BOLD, ITALIC = register_fonts()


def make_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCustom",
            parent=styles["Title"],
            fontName=BOLD,
            fontSize=24,
            leading=28,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontName=REGULAR,
            fontSize=11,
            leading=15,
            textColor=MUTED,
            spaceAfter=12,
        ),
        "h1": ParagraphStyle(
            "H1Custom",
            parent=styles["Heading1"],
            fontName=BOLD,
            fontSize=16,
            leading=19,
            textColor=NAVY,
            spaceBefore=1,
            spaceAfter=7,
        ),
        "h2": ParagraphStyle(
            "H2Custom",
            parent=styles["Heading2"],
            fontName=BOLD,
            fontSize=10.5,
            leading=13,
            textColor=BLUE,
            spaceBefore=6,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "BodyCustom",
            parent=styles["BodyText"],
            fontName=REGULAR,
            fontSize=8.5,
            leading=11.3,
            textColor=INK,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "SmallCustom",
            parent=styles["BodyText"],
            fontName=REGULAR,
            fontSize=7.2,
            leading=9.2,
            textColor=MUTED,
            spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "BulletCustom",
            parent=styles["BodyText"],
            fontName=REGULAR,
            fontSize=8.1,
            leading=10.5,
            textColor=INK,
            leftIndent=11,
            firstLineIndent=-7,
            bulletIndent=2,
            spaceAfter=2,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=styles["BodyText"],
            fontName=BOLD,
            fontSize=8.1,
            leading=10.5,
            textColor=NAVY,
            spaceAfter=0,
        ),
        "table": ParagraphStyle(
            "TableText",
            parent=styles["BodyText"],
            fontName=REGULAR,
            fontSize=7.4,
            leading=9.2,
            textColor=INK,
        ),
        "table_bold": ParagraphStyle(
            "TableBold",
            parent=styles["BodyText"],
            fontName=BOLD,
            fontSize=7.4,
            leading=9.2,
            textColor=INK,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=styles["BodyText"],
            fontName=BOLD,
            fontSize=7.3,
            leading=8.8,
            textColor=WHITE,
            alignment=TA_LEFT,
        ),
        "ref": ParagraphStyle(
            "Reference",
            parent=styles["BodyText"],
            fontName=REGULAR,
            fontSize=7.2,
            leading=9.4,
            textColor=INK,
            leftIndent=14,
            firstLineIndent=-14,
            spaceAfter=3,
        ),
    }


S = make_styles()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def bullet(text: str) -> Paragraph:
    return Paragraph(f"<bullet>-</bullet>{text}", S["bullet"])


def section_title(number: str, title: str, subtitle: str):
    return [
        p(f"{number}  {title}", "h1"),
        p(subtitle, "subtitle"),
        HRFlowable(width="100%", thickness=1.2, color=BLUE, spaceAfter=6),
    ]


def styled_table(data, widths, header=True, font_size=None):
    converted = []
    for row_index, row in enumerate(data):
        converted.append(
            [
                cell
                if hasattr(cell, "wrap")
                else p(str(cell), "table_head" if header and row_index == 0 else "table")
                for cell in row
            ]
        )
    table = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE]),
            ]
        )
    else:
        commands.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, PALE]))
    table.setStyle(TableStyle(commands))
    return table


def callout(label: str, text: str, color=PALE_CYAN):
    table = Table(
        [[p(label, "callout"), p(text, "body")]],
        colWidths=[29 * mm, 145 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("BOX", (0, 0), (-1, -1), 0.7, CYAN),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def flow_table(labels):
    row = []
    widths = []
    for index, label in enumerate(labels):
        row.append(p(label, "table_bold"))
        widths.append(23 * mm)
        if index < len(labels) - 1:
            row.append(p("-&gt;", "table_bold"))
            widths.append(7 * mm)
    table = Table([row], colWidths=widths, hAlign="LEFT")
    commands = [("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for index in range(0, len(row), 2):
        commands.extend(
            [
                ("BACKGROUND", (index, 0), (index, 0), PALE),
                ("BOX", (index, 0), (index, 0), 0.7, BLUE),
                ("LEFTPADDING", (index, 0), (index, 0), 5),
                ("RIGHTPADDING", (index, 0), (index, 0), 5),
                ("TOPPADDING", (index, 0), (index, 0), 7),
                ("BOTTOMPADDING", (index, 0), (index, 0), 7),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def page_frame(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont(REGULAR, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "Cloud Computing Assignment | Arihant Kumar | 230101028")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    if doc.page > 1:
        canvas.setFont(BOLD, 7)
        canvas.setFillColor(NAVY)
        canvas.drawString(18 * mm, height - 12 * mm, "DISTILLED COMMAND PARSER")
        canvas.setStrokeColor(BLUE)
        canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    canvas.restoreState()


def build_story():
    story = []

    # Page 1 - title, scope, architecture and headline evidence.
    story.extend(
        [
            Spacer(1, 7 * mm),
            p("Distilled Command Parser on Local Kubernetes", "title"),
            p(
                "Cloud Computing Assignment Report | Data pipeline, network controls, model distillation and resilient inference",
                "subtitle",
            ),
            styled_table(
                [
                    ["Student", "Roll number", "Submission date"],
                    ["Arihant Kumar", "230101028", "9 November 2026"],
                ],
                [60 * mm, 55 * mm, 59 * mm],
            ),
            Spacer(1, 5 * mm),
            p("Executive summary", "h1"),
            p(
                "This project implements an end-to-end command parsing system on an 8 GB Apple M1 machine. "
                "A Phi-3.5 teacher labelled 3,000 supplied commands in two deterministic Kubernetes jobs. "
                "Validated records were stored in an S3-compatible SeaweedFS service and used to distil "
                "EleutherAI/Pythia-70M. The selected v2 student was packaged behind a strict FastAPI contract, "
                "deployed to k3d, autoscaled under Locust traffic, and tested for pod loss and malformed model output.",
                "body",
            ),
            callout(
                "SCOPE",
                "All numerical claims marked as measured come from committed files in <b>results/</b>. "
                "Cost uses the supplied rate card and is explicitly an estimate, not a cloud invoice.",
            ),
            p("End-to-end architecture", "h2"),
            flow_table(["Command pool", "Phi-3.5 jobs", "SeaweedFS", "Pythia-70M", "FastAPI", "k3d + HPA"]),
            Spacer(1, 5 * mm),
            p("Headline measured outcomes", "h2"),
            styled_table(
                [
                    ["Stage", "Result", "Status"],
                    ["Teacher data", "2,798 clean records from 3,000 inputs", "Complete"],
                    ["Selected student v2", "99% JSON validity; 79% intent; 46% full frame", "Quality gate PASS"],
                    ["Optimized service", "95.12% success; 8.1 s median; 26 s p95", "SLO PASS"],
                    ["Resilience", "8 s pod recovery; 25/25 health probes HTTP 200", "SLO PASS"],
                    ["Release", "10 assets with server-side SHA-256 verification", "Published"],
                ],
                [44 * mm, 95 * mm, 35 * mm],
            ),
            Spacer(1, 4 * mm),
            p(
                "Repository: <link href='https://github.com/kumararihant-06/Cloud_Assignment_1028'>"
                "github.com/kumararihant-06/Cloud_Assignment_1028</link><br/>"
                "Model release: <link href='https://github.com/kumararihant-06/Cloud_Assignment_1028/releases/tag/model-v2'>"
                "releases/tag/model-v2</link>",
                "small",
            ),
            PageBreak(),
        ]
    )

    # Page 2 - Task 1.
    story.extend(section_title("TASK 1", "Distributed teacher labelling and object storage", "Deterministic generation, complete shard coverage, cleaning and provenance"))
    story.extend(
        [
            p("Architecture", "h2"),
            p(
                "The supplied <b>commands_pool.jsonl</b> is uploaded to a SeaweedFS S3 bucket. Two Kubernetes "
                "Jobs partition work by numeric ID modulo two and call a locally hosted Phi-3.5 teacher. Each job "
                "writes an independent JSONL shard. A separate cleaning Job validates the fixed schema, removes "
                "invalid slot values and duplicate commands, balances output deterministically, and writes the "
                "training dataset plus a checksum back to object storage.",
            ),
            flow_table(["3,000 inputs", "2 x 1,500 shards", "Schema checks", "Deduplicate", "train.jsonl", "SHA-256"]),
            p("Implementation", "h2"),
            bullet("Teacher generation uses temperature 0, seed 42, a fixed prompt, bounded retries and no access to validation labels."),
            bullet("Kubernetes Secrets provide S3 credentials at runtime; credentials are generated locally and never committed."),
            bullet("Object keys separate raw teacher shards from <b>datasets/v1/train.jsonl</b>; exports preserve logs and cluster state under <b>results/</b>."),
            bullet("The cleaning algorithm keeps the smallest source ID for duplicate text, making reruns reproducible."),
            p("Measured results", "h2"),
            styled_table(
                [
                    ["Measure", "Observed value"],
                    ["Shard coverage", "1,500 + 1,500; 3,000 unique IDs; none missing or unexpected"],
                    ["Teacher job duration", "Approximately 73 minutes per parallel worker"],
                    ["Rejected records", "153 invalid slot values; 49 duplicate commands"],
                    ["Clean records", "2,798 of 3,000 (93.27%)"],
                    ["Dataset digest", "1331d0275bd00ee6066eccecf6d2e2c492dd1a51a522563d717ec3fbfeb5f2d8"],
                ],
                [48 * mm, 126 * mm],
            ),
            p("Limitations", "h2"),
            bullet("Syntactic validation cannot prove semantic correctness; teacher evaluation later measured only 40% exact full-frame accuracy on 100 labelled examples."),
            bullet("The experiment used one local k3d node and local Ollama, so it does not measure multi-node scheduling, network transfer or managed S3 behaviour."),
            p("Improvements", "h2"),
            bullet("Add a human-reviewed semantic audit sample, per-intent error counts and an explicit low-confidence review queue."),
            bullet("Use checkpointed/resumable shard writes and multiple worker replicas when a multi-node cluster is available."),
            callout(
                "EVIDENCE",
                "results/task1_shard_coverage.json, results/task1_cleaning_report.json, worker/, scripts/export_task1_evidence.py and kubernetes/teacher-workers.yaml",
                PALE,
            ),
            PageBreak(),
        ]
    )

    # Page 3 - Task 2.
    story.extend(section_title("TASK 2", "VLSM subnetting and stateless network ACL", "Capacity-aware address allocation with ordered allow and deny rules"))
    story.extend(
        [
            p("Architecture", "h2"),
            p(
                "The 10.20.0.0/16 address space is allocated largest-first using variable-length subnet masks. "
                "A public-subnet network ACL enforces default deny, permits web ingress, restricts SSH to the "
                "management subnet, permits application traffic on TCP/8000, and explicitly allows ephemeral "
                "reply ports because network ACLs are stateless.",
            ),
            p("Implementation and address plan", "h2"),
            styled_table(
                [
                    ["Subnet", "Need", "CIDR", "Usable range", "Capacity"],
                    ["Application", "1,000", "10.20.0.0/22", "10.20.0.1 - 10.20.3.254", "1,022"],
                    ["Public", "250", "10.20.4.0/24", "10.20.4.1 - 10.20.4.254", "254"],
                    ["Data", "100", "10.20.5.0/25", "10.20.5.1 - 10.20.5.126", "126"],
                    ["Management", "20", "10.20.5.128/27", "10.20.5.129 - 10.20.5.158", "30"],
                ],
                [32 * mm, 18 * mm, 31 * mm, 65 * mm, 28 * mm],
            ),
            bullet("The deny for abusive source 198.51.100.0/24 is rule 50, before the general HTTP/HTTPS allows at rules 100 and 110."),
            bullet("Inbound TCP/22 accepts only 10.20.5.128/27. Inbound replies from the application tier and outbound client replies use TCP 1024-65535."),
            bullet("Outbound TCP/8000 targets only the application subnet. Any unmatched packet is denied."),
            p("Measured results", "h2"),
            callout(
                "6 / 6 PASS",
                "The supplied packet cases were evaluated by <b>tools/nacl_sim.py</b>. Web access, abusive-source precedence, management-only SSH, application forwarding, ephemeral replies and default-deny behaviour matched expectations.",
            ),
            p("Limitations", "h2"),
            bullet("The ACL was validated with deterministic packet cases, not deployed to a public cloud VPC; provider-specific reserved-address and rule-limit behaviour was not exercised."),
            bullet("The design covers IPv4 and TCP only and does not replace host firewalls, security groups, TLS policy or application authentication."),
            p("Improvements", "h2"),
            bullet("Express the plan in Terraform and validate it in an ephemeral cloud account with flow logs and automated reachability tests."),
            bullet("Add IPv6, explicit DNS/NTP requirements, egress filtering and a stateful security-group layer."),
            callout("EVIDENCE", "network/subnets.md, network/nacl.json, network/packets_sample.jsonl, tools/nacl_sim.py and tests/test_network.py", PALE),
            PageBreak(),
        ]
    )

    # Page 4 - Task 3.
    story.extend(section_title("TASK 3", "CPU model distillation and evaluation", "A reproducible Pythia-70M student selected by held-out quality evidence"))
    story.extend(
        [
            p("Architecture", "h2"),
            p(
                "The clean teacher dataset is converted into prompt/target sequences for EleutherAI/Pythia-70M. "
                "Loss is masked on prompt tokens so optimization learns only the JSON target. Training runs on CPU "
                "with fixed seeds and writes model, tokenizer, loss history, package versions and SHA-256 manifests "
                "to SeaweedFS. Four systems are evaluated on the same 100-example labelled validation set.",
            ),
            p("Implementation", "h2"),
            bullet("Shared configuration: 1,500 training examples, batch size 4, learning rate 5e-5, maximum sequence length 192 and gradient clipping at 1.0."),
            bullet("v1 uses seed 42 for 3 epochs. v2 changes only seed to 43 and trains for 4 epochs, preserving a controlled comparison."),
            bullet("The parser enforces exactly five keys: intent, date, time, place and no additional fields. A 95% JSON-validity gate selects release candidates."),
            p("Measured training results", "h2"),
            styled_table(
                [
                    ["Run", "CPU wall time", "Epoch losses", "Final model SHA-256"],
                    ["v1", "~6 min 42 s", "0.3885, 0.1970, 0.1547", "3606a3fd...3a6f11a"],
                    ["v2", "~5 min 14 s", "0.3822, 0.2053, 0.1693, 0.1378", "a1fe3929...b92e8c"],
                ],
                [25 * mm, 33 * mm, 66 * mm, 50 * mm],
            ),
            p("Measured evaluation on 100 examples", "h2"),
            styled_table(
                [
                    ["System", "JSON valid", "Intent", "Date", "Time", "Place", "Full frame"],
                    ["Untrained Pythia", "0%", "0%", "0%", "0%", "0%", "0%"],
                    ["Phi-3.5 teacher", "100%", "79%", "77%", "85%", "76%", "40%"],
                    ["Student v1", "97%", "76%", "75%", "79%", "77%", "36%"],
                    ["Student v2", "99%", "79%", "80%", "89%", "83%", "46%"],
                ],
                [42 * mm, 25 * mm, 21 * mm, 21 * mm, 21 * mm, 21 * mm, 23 * mm],
            ),
            callout("SELECTION", "v2 passed the 95% validity gate, tied the teacher on intent accuracy and achieved the best slot and full-frame scores."),
            p("Limitations", "h2"),
            bullet("The validation set contains only 100 examples; full-frame accuracy of 46% remains insufficient for high-stakes automation."),
            bullet("Student quality inherits teacher noise, and only 1,500 of 2,798 clean examples were used to keep CPU training practical."),
            p("Improvements", "h2"),
            bullet("Use all clean data, a larger stratified gold set, constrained JSON decoding, error-driven augmentation and confidence calibration."),
            bullet("Benchmark quantization and compact classification/slot models to reduce latency while retaining schema validity."),
            PageBreak(),
        ]
    )

    # Page 5 - Task 4 architecture and implementation.
    story.extend(section_title("TASK 4", "Containerized inference and Kubernetes operations", "Strict API contracts, verified model loading, autoscaling and defensive deployment"))
    story.extend(
        [
            p("Architecture", "h2"),
            flow_table(["GitHub/SeaweedFS", "Init download", "SHA-256 check", "FastAPI", "Service", "Ingress + HPA"]),
            p(
                "At pod startup, the selected v2 artifact is downloaded from S3-compatible storage and verified "
                "against <b>model.sha256</b>. Readiness stays false until the tokenizer and model load. FastAPI "
                "validates requests, normalizes model output and rejects malformed or extra-key JSON with a "
                "controlled HTTP 500. Kubernetes exposes the workload through a ClusterIP Service and Traefik ingress.",
            ),
            p("Implementation", "h2"),
            styled_table(
                [
                    ["Concern", "Implemented control"],
                    ["API contract", "POST /parse; strict request and five-key response schemas; model version and serving pod headers"],
                    ["Health", "Separate /healthz and /readyz endpoints with startup, liveness and readiness probes"],
                    ["Scaling", "HPA minimum 2, maximum 4, target 60% average CPU; 500m CPU request per pod"],
                    ["Resources", "2 CPU and 1 GiB limits; 512 MiB memory request; four inference threads"],
                    ["Availability", "Rolling updates, topology spread and PodDisruptionBudget minAvailable 1"],
                    ["Container security", "UID 10001, read-only root filesystem, no privilege escalation and all Linux capabilities dropped"],
                    ["Supply integrity", "Model files excluded from Git; startup checksum validation; GitHub Release checksum manifest"],
                ],
                [45 * mm, 129 * mm],
            ),
            p("Test strategy", "h2"),
            bullet("Unit tests cover cleaning, training masks/configuration, strict schema handling, API behaviour, cost arithmetic and manifest constraints."),
            bullet("Integration evidence includes image build, Kubernetes rollout state, HTTP response headers, Locust history, HPA state and fault injection."),
            bullet("GitHub Actions runs tests, selected-model quality gate, NACL cases, cost recalculation, container build and a full-history Gitleaks scan."),
            p("Operational flow", "h2"),
            styled_table(
                [
                    ["Build", "Deploy", "Observe", "Shutdown"],
                    ["docker build / make service-image", "make service-deploy", "make service-status; curl; Locust", "make service-down; make down"],
                ],
                [43.5 * mm] * 4,
            ),
            callout(
                "DESIGN CHOICE",
                "A two-replica minimum preserves service during one-pod loss. HPA reaches four replicas under measured CPU saturation, while the PDB protects voluntary disruptions.",
                PALE,
            ),
            PageBreak(),
        ]
    )

    # Page 6 - Task 4 results, limitations and improvements.
    story.extend(section_title("TASK 4", "Measured performance, resilience and cost", "Baseline-to-optimized comparison and explicit operating assumptions"))
    story.extend(
        [
            p("Measured Locust results: 4 users, spawn rate 4/s, 2 minutes", "h2"),
            styled_table(
                [
                    ["Metric", "1 CPU baseline", "2 CPU optimized", "Change"],
                    ["Requests", "17", "41", "+24"],
                    ["Success rate", "41.18%", "95.12%", "+53.94 percentage points"],
                    ["Throughput", "0.1451 req/s", "0.3437 req/s", "2.37x"],
                    ["Average latency", "25.66 s", "10.65 s", "-58.50%"],
                    ["Median latency", "30.0 s", "8.1 s", "-73.00%"],
                    ["p95 latency", "30.0 s", "26.0 s", "-13.33%"],
                ],
                [44 * mm, 41 * mm, 43 * mm, 46 * mm],
            ),
            p(
                "The baseline saturated one CPU per pod and timed out during HPA scale-up. A controlled 45-second "
                "probe at a two-CPU limit produced 8/8 successes, motivating the final setting. In the complete "
                "optimized run, 39/41 requests succeeded; the remaining two timeouts occurred while HPA moved from two to four ready replicas.",
            ),
            p("Measured resilience", "h2"),
            styled_table(
                [
                    ["Experiment", "Observed result"],
                    ["Single-pod deletion", "Replacement ready in 8 seconds; 25/25 ingress health probes returned HTTP 200"],
                    ["Malformed model output", "Injected response HTTP 500 with {error: invalid_model_output}; restored response HTTP 200"],
                    ["Model traceability", "39/39 successful load responses reported v2 and were distributed across four serving pods"],
                ],
                [52 * mm, 122 * mm],
            ),
            p("Cost estimate and SLO status", "h2"),
            styled_table(
                [
                    ["Item", "Value", "Classification"],
                    ["Four-replica cost", "INR 29.80/hour", "Assumption from supplied rate card"],
                    ["Cost per 1,000 attempted", "INR 24.0843", "Estimate using measured throughput"],
                    ["Cost per 1,000 successful", "INR 25.3194", "Estimate using measured success ratio"],
                    ["Quality / success / p95 / recovery SLOs", "99% / 95.12% / 26 s / 8 s", "Measured; all PASS"],
                ],
                [62 * mm, 55 * mm, 57 * mm],
            ),
            p("Limitations", "h2"),
            bullet("The two-minute local test is not a production endurance test. Latency includes CPU generation on an M1 Docker/k3d environment and cannot be generalized to cloud hardware."),
            bullet("Cold HPA reconciliation caused two timeouts. The cost model assumes four replicas remain active and bills declared limits continuously; no cloud invoice was observed."),
            p("Improvements", "h2"),
            bullet("Pre-warm four replicas for burst windows, tune HPA behaviour, add a queue with backpressure, and test longer step-load and soak scenarios."),
            bullet("Quantize or replace the generative parser with a smaller structured model; add OpenTelemetry, dashboards, alerts and canary rollback."),
            PageBreak(),
        ]
    )

    # Page 7 - validation, provenance and reproducibility.
    story.extend(section_title("VALIDATION", "Reproducibility, security and provenance", "Every deliverable is linked to executable code, immutable evidence or a checksum"))
    story.extend(
        [
            p("Verification layers", "h2"),
            styled_table(
                [
                    ["Layer", "Verification"],
                    ["Source", "Git history with student-controlled commits; final code organized by data, worker, training, evaluation, service, Kubernetes, network and tools"],
                    ["Automated tests", "29 local unit/manifest tests passed; CI run 2 completed successfully on commit 88a94f4"],
                    ["Security", "Gitleaks full-history scan passed; generated Secrets and model weights are excluded from Git"],
                    ["Data", "Complete 3,000-ID shard coverage and immutable clean-dataset SHA-256"],
                    ["Model", "SeaweedFS manifests verified; GitHub server digest equals local selected-model digest"],
                    ["Deployment", "Captured rollout, HPA, headers, Locust, pod-loss and injected-failure evidence"],
                ],
                [42 * mm, 132 * mm],
            ),
            p("Release provenance", "h2"),
            p(
                "The public <b>model-v2</b> GitHub Release targets commit 88a94f497f98edd1a97d6ff761ccb07c79c72d0a. "
                "It contains ten assets: model weights, tokenizer files, configurations, loss history, version metadata, "
                "the training checksum and a release-wide SHA256SUMS file. The 281,715,176-byte model digest is "
                "<b>a1fe3929360f76faa8f769219b4479919305f710a7155c0dafa835ba86b92e8c</b>.",
            ),
            p("Measured facts versus assumptions", "h2"),
            styled_table(
                [
                    ["Measured directly", "Assumed or project-defined"],
                    ["Data counts, checksums, training loss/time and 100-example evaluation", "The 100-example sample represents future traffic"],
                    ["Two Locust runs, response headers, HPA observations and CPU limits", "Four replicas are a suitable steady-state costing point"],
                    ["Pod replacement time, health responses and malformed-output behaviour", "Local-cluster resilience predicts multi-node cloud behaviour"],
                    ["CI job conclusions and GitHub asset digests", "Supplied rate-card prices represent deployable cloud cost"],
                ],
                [87 * mm, 87 * mm],
            ),
            p("Reproduction sequence", "h2"),
            p(
                "1. <b>make cluster-up storage-bootstrap</b> &nbsp; 2. start Ollama/Phi-3.5 &nbsp; "
                "3. <b>make teacher-jobs clean-data task1-evidence</b> &nbsp; 4. train/evaluate v1 and v2 &nbsp; "
                "5. <b>make service-deploy load-test cost-analysis</b> &nbsp; 6. run tests, scan, release checksums and shutdown.",
            ),
            callout(
                "AI DISCLOSURE",
                "OpenAI Codex assisted planning, coding and diagnosis. The student reviewed changes, executed every commit/push and retained responsibility for design and verification. AI suggestions are not used as evidence; see AI_USE.md.",
                PALE_AMBER,
            ),
            PageBreak(),
        ]
    )

    # Page 8 - conclusion and references.
    story.extend(section_title("CONCLUSION", "Findings and next steps", "A complete local cloud-native ML system with transparent evidence and known limits"))
    story.extend(
        [
            p("Key findings", "h2"),
            bullet("Deterministic sharding and checksum-backed object storage made a long teacher-labelling stage auditable and repeatable."),
            bullet("The 70M student matched teacher intent accuracy and improved exact full-frame accuracy from 40% to 46%, but semantic quality remains the main system constraint."),
            bullet("CPU allocation dominated inference reliability: raising the limit from one to two CPUs reduced failures from 58.82% to 4.88% and increased throughput 2.37x."),
            bullet("Replica redundancy and a PDB prevented observed health downtime during one-pod loss, while strict schema handling converted malformed output into a controlled error."),
            p("Prioritized improvements", "h2"),
            styled_table(
                [
                    ["Priority", "Improvement", "Expected effect"],
                    ["1", "Constrained decoding plus larger human-reviewed validation set", "Higher semantic and full-frame confidence"],
                    ["2", "Quantized or discriminative parser", "Lower latency and cost on CPU"],
                    ["3", "HPA pre-warming, tuned behaviour and request queue", "Remove burst-window timeouts"],
                    ["4", "Multi-node cloud test, flow logs and IaC", "Validate failure-domain and network assumptions"],
                    ["5", "Soak tests, tracing, dashboards and alerts", "Operational confidence beyond short local runs"],
                ],
                [22 * mm, 79 * mm, 73 * mm],
            ),
            p("References", "h2"),
            p("[1] Assignment-supplied command pool, validation labels, schema, packet cases and rate card, 2026.", "ref"),
            p("[2] EleutherAI, Pythia-70M model card. https://huggingface.co/EleutherAI/pythia-70m", "ref"),
            p("[3] Microsoft, Phi-3.5 Mini Instruct model card. https://huggingface.co/microsoft/Phi-3.5-mini-instruct", "ref"),
            p("[4] SeaweedFS documentation. https://github.com/seaweedfs/seaweedfs", "ref"),
            p("[5] Kubernetes, Horizontal Pod Autoscaling. https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/", "ref"),
            p("[6] Kubernetes, Configure liveness, readiness and startup probes. https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/", "ref"),
            p("[7] FastAPI documentation. https://fastapi.tiangolo.com/", "ref"),
            p("Evidence index", "h2"),
            p(
                "Primary measurements are in results/evaluation_summary.json, training_v1.txt, training_v2.txt, "
                "loadtest_baseline_summary.txt, loadtest_optimized_summary.txt, reliability.txt, cost.json, slo.json, "
                "ci.txt and release.txt. Build, deploy, test and shutdown commands are documented in README.md.",
                "small",
            ),
            Spacer(1, 3 * mm),
            HRFlowable(width="100%", thickness=1.0, color=BLUE, spaceAfter=5),
            p(
                "Final assessment: the project satisfies the required data, networking, training, deployment, "
                "testing, evidence and release workflow. Its measured limitations are reported rather than hidden, "
                "and the repository provides a reproducible path from source data to shutdown.",
                "callout",
            ),
        ]
    )
    return story


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Distilled Command Parser on Local Kubernetes",
        author="Arihant Kumar (230101028)",
        subject="Cloud Computing Assignment Report",
        creator="ReportLab",
    )
    doc.build(build_story(), onFirstPage=page_frame, onLaterPages=page_frame)

    reader = PdfReader(str(output))
    if not 1 <= len(reader.pages) <= 8:
        raise RuntimeError(f"Report must be at most 8 pages; generated {len(reader.pages)}")
    if not all((page.extract_text() or "").strip() for page in reader.pages):
        raise RuntimeError("Generated report contains an empty page")
    print(f"Wrote {output} ({len(reader.pages)} pages, {output.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("report/report.pdf"))
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
