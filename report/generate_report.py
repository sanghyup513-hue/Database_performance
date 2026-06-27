#!/usr/bin/env python3
"""
JMeter JTL 결과 → 집계 → 고객 제공용 PDF 리포트 생성.

입력: 결과 디렉터리의 JTL 파일들. 파일명 규칙: {db}__{NN}_{testtype}.jtl
      db ∈ {pg, alti} (run_meta.json 의 databases 키와 일치)
      예) pg__01_read_only.jtl, alti__03_mixed_oltp.jtl
출력: PDF (기본 report.pdf) + 차트 PNG(임시).

의존성: pandas, matplotlib, reportlab
실행:   python generate_report.py --results <dir> --meta run_meta.json --out report.pdf
"""
import argparse, glob, json, os, re, tempfile
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, PageBreak, Flowable)

# ── 한국어 폰트 (reportlab 내장 CID, 외부 폰트 불필요) ──
KFONT = "HYSMyeongJo-Medium"
pdfmetrics.registerFont(UnicodeCIDFont(KFONT))

TESTTYPES = [
    ("01_read_only",        "Read-only",        "포인트 조회·범위 스캔·조인 (SELECT)"),
    ("02_write_heavy",      "Write-heavy",      "UPDATE / INSERT 위주"),
    ("03_mixed_oltp",       "Mixed OLTP",       "TPC-B류 트랜잭션 믹스"),
    ("04_high_concurrency", "High-concurrency", "동시성 단계 증가"),
    ("05_large_workload",   "Large workload",   "대용량 스캔·집계·조인 + 배치 DML"),
]
TT_ORDER = [t[0] for t in TESTTYPES]
TT_NAME = {t[0]: t[1] for t in TESTTYPES}
TT_DESC = {t[0]: t[2] for t in TESTTYPES}

FNAME_RE = re.compile(r"^(?P<db>[a-z0-9]+)__(?P<key>\d{2}_[a-z_]+)\.jtl$", re.I)


def load_meta(path):
    default = {
        "title": "DB 성능 비교 벤치마크", "subtitle": "", "date": "",
        "draft": False,
        "databases": {"pg": {"label": "PostgreSQL", "color": "#336791"},
                      "alti": {"label": "Altibase", "color": "#E4572E"}},
        "environment": {},
    }
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            default.update(json.load(f))
    return default


def summarize_jtl(path):
    df = pd.read_csv(path, usecols=["timeStamp", "elapsed", "success"],
                     dtype={"success": str}, on_bad_lines="skip")
    if df.empty:
        return None
    n = len(df)
    ok = df["success"].str.lower().eq("true")
    errors = int((~ok).sum())
    wall = (df["timeStamp"].max() - df["timeStamp"].min()) / 1000.0
    wall = wall if wall > 0 else 1.0
    el = df["elapsed"].astype(float)
    return {
        "samples": n,
        "errors": errors,
        "error_rate": 100.0 * errors / n,
        "throughput": n / wall,
        "avg": el.mean(),
        "p50": el.quantile(0.50),
        "p90": el.quantile(0.90),
        "p95": el.quantile(0.95),
        "p99": el.quantile(0.99),
        "duration_s": wall,
    }


def discover(results_dir):
    """returns {db: {key: summary}}"""
    data = {}
    for p in sorted(glob.glob(os.path.join(results_dir, "*.jtl"))):
        m = FNAME_RE.match(os.path.basename(p))
        if not m:
            continue
        db, key = m.group("db").lower(), m.group("key").lower()
        if key not in TT_ORDER:
            continue
        s = summarize_jtl(p)
        if s:
            data.setdefault(db, {})[key] = s
    return data


def bar_chart(data, dbs, meta, metric, ylabel, title, outpath, lower_better=False):
    keys = [k for k in TT_ORDER if any(k in data.get(db, {}) for db in dbs)]
    if not keys:
        return None
    labels = [TT_NAME[k] for k in keys]
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    nb = len(dbs)
    width = 0.8 / max(nb, 1)
    for i, db in enumerate(dbs):
        vals = [data.get(db, {}).get(k, {}).get(metric, 0) for k in keys]
        xs = [j + (i - (nb - 1) / 2) * width for j in range(len(keys))]
        ax.bar(xs, vals, width=width, label=meta["databases"][db]["label"],
               color=meta["databases"][db]["color"])
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title + ("  (lower is better)" if lower_better else "  (higher is better)"),
                 fontsize=10, weight="bold")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")
    plt.close(fig)
    return outpath


class HRule(Flowable):
    def __init__(self, width, color=colors.HexColor("#336791"), thick=1.2):
        super().__init__(); self.width = width; self.color = color; self.thick = thick
    def draw(self):
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(self.thick)
        self.canv.line(0, 0, self.width, 0)


def styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", fontName=KFONT, fontSize=24, leading=30,
                                alignment=TA_CENTER, textColor=colors.HexColor("#1b2a4a")),
        "sub": ParagraphStyle("s", fontName=KFONT, fontSize=13, leading=18,
                              alignment=TA_CENTER, textColor=colors.HexColor("#555")),
        "h1": ParagraphStyle("h1", fontName=KFONT, fontSize=15, leading=20,
                             spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1b2a4a")),
        "h2": ParagraphStyle("h2", fontName=KFONT, fontSize=12, leading=16,
                             spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#33506e")),
        "body": ParagraphStyle("b", fontName=KFONT, fontSize=10, leading=15),
        "small": ParagraphStyle("sm", fontName=KFONT, fontSize=8, leading=11,
                                textColor=colors.HexColor("#666")),
        "cell": ParagraphStyle("c", fontName=KFONT, fontSize=8.5, leading=11),
        "cellb": ParagraphStyle("cb", fontName=KFONT, fontSize=8.5, leading=11,
                               textColor=colors.white),
    }


def metrics_table(data, dbs, meta, st):
    """per test-type metrics table"""
    head = ["테스트 유형"]
    for db in dbs:
        lbl = meta["databases"][db]["label"]
        head += [f"{lbl}\nTPS", "p95(ms)", "p99(ms)", "에러%"]
    rows = [[Paragraph(h.replace("\n", "<br/>"), st["cellb"]) for h in head]]
    for k in TT_ORDER:
        if not any(k in data.get(db, {}) for db in dbs):
            continue
        row = [Paragraph(TT_NAME[k], st["cell"])]
        for db in dbs:
            s = data.get(db, {}).get(k)
            if s:
                row += [Paragraph(f"{s['throughput']:,.0f}", st["cell"]),
                        Paragraph(f"{s['p95']:.0f}", st["cell"]),
                        Paragraph(f"{s['p99']:.0f}", st["cell"]),
                        Paragraph(f"{s['error_rate']:.2f}", st["cell"])]
            else:
                row += [Paragraph("—", st["cell"])] * 4
        rows.append(row)
    ncol = 1 + 4 * len(dbs)
    cw = [38 * mm] + [(150 * mm - 38 * mm) / (ncol - 1)] * (ncol - 1)
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#33506e")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def env_table(meta, st):
    rows = []
    for k, v in meta.get("environment", {}).items():
        rows.append([Paragraph(k, st["cellb"]), Paragraph(str(v), st["cell"])])
    t = Table(rows, colWidths=[40 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#33506e")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(KFONT, 8)
    canvas.setFillColor(colors.HexColor("#888"))
    canvas.drawRightString(200 * mm, 10 * mm, f"- {doc.page} -")
    canvas.drawString(20 * mm, 10 * mm, "DB 성능 비교 벤치마크 (자동 생성)")
    canvas.restoreState()


def build(data, meta, charts, outpath):
    st = styles()
    dbs = [db for db in meta["databases"] if db in data] or list(meta["databases"])
    present = [db for db in meta["databases"] if db in data]
    doc = SimpleDocTemplate(outpath, pagesize=A4, topMargin=20 * mm,
                            bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm)
    E = []
    # ── Cover ──
    E += [Spacer(1, 55 * mm),
          Paragraph(meta["title"], st["title"]), Spacer(1, 6 * mm),
          Paragraph(meta.get("subtitle", ""), st["sub"]), Spacer(1, 4 * mm)]
    if meta.get("draft"):
        E += [Paragraph("※ DRAFT — 일부 DB 미측정 / 본 측정 전 초안", st["sub"])]
    E += [Spacer(1, 10 * mm), HRule(150 * mm), Spacer(1, 3 * mm),
          Paragraph(f"작성일: {meta.get('date','')}", st["sub"]), PageBreak()]

    # ── Executive summary ──
    E += [Paragraph("1. 핵심 요약 (Executive Summary)", st["h1"]), HRule(165 * mm), Spacer(1, 4 * mm)]
    if len(present) >= 2:
        summary = "두 DB를 동일한 JMeter 워크로드로 측정한 결과를 테스트 유형별로 비교한다. 아래 표와 차트가 처리량(TPS)과 지연시간(p95/p99)의 차이를 요약한다."
    elif present:
        lbl = meta["databases"][present[0]]["label"]
        summary = (f"현재 <b>{lbl}</b> 측정값만 포함된 초안이다. Altibase 측정값이 확보되면 동일 절차로 비교 컬럼이 채워진다. "
                   "아래는 측정된 DB의 유형별 처리량·지연시간 요약이다.")
    else:
        summary = "측정 데이터가 없습니다."
    E += [Paragraph(summary, st["body"]), Spacer(1, 5 * mm),
          metrics_table(data, present or dbs, meta, st), Spacer(1, 4 * mm),
          Paragraph("TPS는 높을수록, 지연시간(p95/p99)은 낮을수록 우수.", st["small"]), PageBreak()]

    # ── Environment / method ──
    E += [Paragraph("2. 테스트 환경 및 방법", st["h1"]), HRule(165 * mm), Spacer(1, 4 * mm),
          env_table(meta, st), Spacer(1, 4 * mm),
          Paragraph("측정 지표는 TPS(처리량), 지연시간 p50/p95/p99, 에러율이다. 부하는 K8s 클러스터의 "
                    "JMeter가 JDBC로 생성하며, 두 DB에 동일한 테스트 계획·스케일을 적용한다.", st["body"]), PageBreak()]

    # ── Charts ──
    E += [Paragraph("3. 유형별 결과", st["h1"]), HRule(165 * mm), Spacer(1, 3 * mm)]
    for cap, img in charts:
        if img and os.path.exists(img):
            E += [Paragraph(cap, st["h2"]), Image(img, width=165 * mm, height=74 * mm), Spacer(1, 4 * mm)]
    E += [PageBreak()]

    # ── Appendix: full numbers ──
    E += [Paragraph("부록. 상세 수치", st["h1"]), HRule(165 * mm), Spacer(1, 4 * mm)]
    for db in (present or dbs):
        E += [Paragraph(meta["databases"][db]["label"], st["h2"])]
        head = ["유형", "샘플수", "TPS", "avg", "p50", "p90", "p95", "p99", "에러%"]
        rows = [[Paragraph(h, st["cellb"]) for h in head]]
        for k in TT_ORDER:
            s = data.get(db, {}).get(k)
            if not s:
                continue
            rows.append([Paragraph(x, st["cell"]) for x in [
                TT_NAME[k], f"{s['samples']:,}", f"{s['throughput']:,.0f}", f"{s['avg']:.0f}",
                f"{s['p50']:.0f}", f"{s['p90']:.0f}", f"{s['p95']:.0f}", f"{s['p99']:.0f}",
                f"{s['error_rate']:.2f}"]])
        t = Table(rows, colWidths=[30*mm,20*mm,18*mm,15*mm,15*mm,15*mm,15*mm,15*mm,15*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#33506e")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")]),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        E += [t, Spacer(1, 5 * mm)]

    doc.build(E, onFirstPage=lambda c, d: None, onLaterPages=footer)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--meta", default="run_meta.json")
    ap.add_argument("--out", default="report.pdf")
    a = ap.parse_args()
    meta = load_meta(a.meta)
    data = discover(a.results)
    present = [db for db in meta["databases"] if db in data]
    print("측정된 DB:", present or "(없음)")
    for db in present:
        print(" ", db, "유형:", sorted(data[db].keys()))
    tmp = tempfile.mkdtemp()
    charts = [
        ("처리량 (TPS, 높을수록 우수)",
         bar_chart(data, present, meta, "throughput", "req/s", "Throughput by test type",
                   os.path.join(tmp, "tps.png"))),
        ("지연시간 p95 (ms, 낮을수록 우수)",
         bar_chart(data, present, meta, "p95", "ms", "p95 latency by test type",
                   os.path.join(tmp, "p95.png"), lower_better=True)),
        ("지연시간 p99 (ms, 낮을수록 우수)",
         bar_chart(data, present, meta, "p99", "ms", "p99 latency by test type",
                   os.path.join(tmp, "p99.png"), lower_better=True)),
    ]
    build(data, meta, charts, a.out)
    print("PDF 생성:", a.out)


if __name__ == "__main__":
    main()
