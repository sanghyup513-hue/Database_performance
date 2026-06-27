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
import argparse, base64, glob, html, json, os, re, tempfile
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


def build_html(data, meta, charts, outpath):
    """자체완결형 HTML 조각 (Artifact용: html/head/body 태그 없이 title+style+content)."""
    present = [db for db in meta["databases"] if db in data]
    dbs = present or list(meta["databases"])

    def esc(x): return html.escape(str(x))

    def b64img(path):
        if not path or not os.path.exists(path):
            return ""
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()

    # summary table
    def summary_rows():
        out = []
        head = "<th>테스트 유형</th>"
        for db in dbs:
            lbl = esc(meta["databases"][db]["label"])
            head += f"<th>{lbl} TPS</th><th>p95(ms)</th><th>p99(ms)</th><th>에러%</th>"
        out.append("<tr>" + head + "</tr>")
        for k in TT_ORDER:
            if not any(k in data.get(db, {}) for db in dbs):
                continue
            row = f"<td class='lt'>{esc(TT_NAME[k])}</td>"
            for db in dbs:
                s = data.get(db, {}).get(k)
                if s:
                    row += (f"<td>{s['throughput']:,.0f}</td><td>{s['p95']:.0f}</td>"
                            f"<td>{s['p99']:.0f}</td><td>{s['error_rate']:.2f}</td>")
                else:
                    row += "<td>—</td><td>—</td><td>—</td><td>—</td>"
            out.append("<tr>" + row + "</tr>")
        return "\n".join(out)

    def appendix(db):
        head = ("<tr><th>유형</th><th>샘플수</th><th>TPS</th><th>avg</th><th>p50</th>"
                "<th>p90</th><th>p95</th><th>p99</th><th>에러%</th></tr>")
        rows = [head]
        for k in TT_ORDER:
            s = data.get(db, {}).get(k)
            if not s:
                continue
            rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in [
                esc(TT_NAME[k]), f"{s['samples']:,}", f"{s['throughput']:,.0f}", f"{s['avg']:.0f}",
                f"{s['p50']:.0f}", f"{s['p90']:.0f}", f"{s['p95']:.0f}", f"{s['p99']:.0f}",
                f"{s['error_rate']:.2f}"]) + "</tr>")
        return "\n".join(rows)

    env_rows = "\n".join(
        f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in meta.get("environment", {}).items())
    chart_html = "\n".join(
        f"<h3>{esc(cap)}</h3><img class='chart' src='{b64img(img)}' alt='{esc(cap)}'/>"
        for cap, img in charts if img)
    appendix_html = "\n".join(
        f"<h3>{esc(meta['databases'][db]['label'])}</h3>"
        f"<div class='tw'><table class='data'>{appendix(db)}</table></div>" for db in dbs)
    draft = ("<div class='badge'>DRAFT — 일부 DB 미측정 / 본 측정 전 초안</div>"
             if meta.get("draft") else "")

    css = """
    :root{--navy:#1b2a4a;--blue:#33506e;--line:#d4dbe6;--bg:#f3f6fa;}
    *{box-sizing:border-box;}
    .rpt{max-width:860px;margin:0 auto;padding:0 4px;color:#1c2430;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.55;}
    .cover{background:linear-gradient(135deg,var(--navy),#33506e);color:#fff;border-radius:14px;
      padding:34px 22px;text-align:center;margin:8px 0 18px;}
    .cover h1{font-size:24px;margin:0 0 8px;line-height:1.3;}
    .cover .sub{opacity:.9;font-size:14px;margin:0 0 6px;}
    .cover .date{opacity:.75;font-size:12px;margin-top:14px;}
    .badge{display:inline-block;background:#ffce54;color:#5a4500;font-weight:700;font-size:12px;
      padding:4px 12px;border-radius:20px;margin-top:10px;}
    h2{color:var(--navy);font-size:18px;border-bottom:2px solid var(--blue);padding-bottom:6px;margin:26px 0 12px;}
    h3{color:var(--blue);font-size:14px;margin:18px 0 6px;}
    p{font-size:14px;} .note{color:#667;font-size:12px;}
    .tw{overflow-x:auto;-webkit-overflow-scrolling:touch;}
    table{border-collapse:collapse;width:100%;font-size:13px;min-width:480px;margin:6px 0;}
    th,td{border:1px solid var(--line);padding:7px 9px;text-align:center;}
    th{background:var(--blue);color:#fff;font-weight:600;}
    td.lt{text-align:left;font-weight:600;}
    tr:nth-child(even) td{background:var(--bg);}
    table.env{min-width:0;} table.env th{width:38%;text-align:left;}
    table.env td{text-align:left;}
    img.chart{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;margin:4px 0 8px;}
    @media(max-width:600px){.cover h1{font-size:20px;}h2{font-size:16px;}}
    """
    title = esc(meta.get("title", "DB 성능 비교 벤치마크"))
    doc = f"""<title>{title}</title>
<style>{css}</style>
<div class="rpt">
  <div class="cover">
    <h1>{title}</h1>
    <div class="sub">{esc(meta.get('subtitle',''))}</div>
    {draft}
    <div class="date">작성일: {esc(meta.get('date',''))}</div>
  </div>

  <h2>1. 핵심 요약</h2>
  <p class="note">TPS는 높을수록, 지연시간(p95/p99)은 낮을수록 우수.</p>
  <div class="tw"><table>{summary_rows()}</table></div>

  <h2>2. 테스트 환경 및 방법</h2>
  <table class="env">{env_rows}</table>
  <p class="note">측정 지표: TPS·지연시간 p50/p95/p99·에러율. K8s의 JMeter가 JDBC로 부하 생성, 두 DB에 동일 계획·스케일 적용.</p>

  <h2>3. 유형별 결과</h2>
  {chart_html}

  <h2>부록. 상세 수치</h2>
  {appendix_html}
</div>
"""
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--meta", default="run_meta.json")
    ap.add_argument("--out", default="report.pdf")
    ap.add_argument("--html", default=None, help="자체완결형 HTML 조각 출력 경로")
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
    if a.html:
        build_html(data, meta, charts, a.html)
        print("HTML 생성:", a.html)


if __name__ == "__main__":
    main()
