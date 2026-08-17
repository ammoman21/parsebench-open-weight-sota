#!/usr/bin/env python
"""
Synthetic chart-extraction training data.

Pair = (rendered chart image, markdown the chart scorer can match). Format per the
execution-verified scoring spec: title as a `#` heading ABOVE a pipe table whose
column headers are the series names (or a Series column); data points must appear
with correct labels. Prompt is the pipeline's own chart-stage trigger,
"\nImage Analysis:\n" — byte-identical to production, same principle as the text
fine-tune.

Two difficulty tiers on purpose:
  - value-labelled charts (numbers printed on bars/points): teaches the FORMAT
  - unlabelled charts: teaches actual axis reading
Insurance-flavoured content throughout, matching the corpus.
"""
import argparse, json, random, shutil
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
TITLES = ["Combined Ratio by Segment", "Gross Written Premium by Line", "Loss Ratio Trend",
          "Expense Ratio by Region", "Claims Frequency by Quarter", "Reserve Development",
          "Premium Growth by Channel", "Retention Rate by Cohort", "Cat Losses by Peril",
          "Underwriting Margin by Product"]
CATS = [["Auto","Home","Commercial","Life"], ["Q1","Q2","Q3","Q4"],
        ["North","South","East","West"], ["2021","2022","2023","2024","2025"],
        ["Agency","Direct","Broker"], ["Wind","Hail","Flood","Fire"]]
SERIES = [["Actual"], ["2024","2025"], ["Gross","Net"], ["Target","Actual"]]

def one_chart(rng, idx, outdir):
    kind = rng.choice(["bar","bar","line","pie"])   # bars dominate the corpus
    title = rng.choice(TITLES)
    cats = rng.choice(CATS)
    series = rng.choice(SERIES) if kind != "pie" else ["Share"]
    labelled = rng.random() < 0.55
    data = {s: [round(rng.uniform(5, 95), 1) for _ in cats] for s in series}

    fig, ax = plt.subplots(figsize=(rng.uniform(4.5,6.5), rng.uniform(3.2,4.5)), dpi=110)
    if kind == "bar":
        w = 0.8 / len(series)
        for i, s in enumerate(series):
            xs = [j + i*w for j in range(len(cats))]
            bars = ax.bar(xs, data[s], width=w, label=s)
            if labelled:
                for b, v in zip(bars, data[s]):
                    ax.text(b.get_x()+b.get_width()/2, v, f"{v}", ha="center",
                            va="bottom", fontsize=7)
        ax.set_xticks([j + 0.4 - w/2 for j in range(len(cats))]); ax.set_xticklabels(cats)
    elif kind == "line":
        for s in series:
            ax.plot(range(len(cats)), data[s], marker="o", label=s)
            if labelled:
                for j, v in enumerate(data[s]):
                    ax.annotate(f"{v}", (j, v), fontsize=7, xytext=(0,4),
                                textcoords="offset points", ha="center")
        ax.set_xticks(range(len(cats))); ax.set_xticklabels(cats)
    else:
        vals = [data["Share"][i] for i in range(len(cats))]
        tot = sum(vals); vals = [round(v*100/tot, 1) for v in vals]
        data = {"Share": vals}
        ax.pie(vals, labels=cats, autopct=(lambda p: f"{p:.1f}") if labelled else None)
    if kind != "pie":
        if len(series) > 1 and rng.random() < 0.9: ax.legend(fontsize=8)
        if rng.random() < 0.6: ax.grid(axis="y", alpha=0.3)
    ax.set_title(title, fontsize=11)
    png = outdir / f"chart_{idx:05d}.png"
    fig.tight_layout(); fig.savefig(png); plt.close(fig)

    header = "| Category | " + " | ".join(series) + " |"
    sep = "|" + "---|" * (len(series) + 1)
    rows = [f"| {c} | " + " | ".join(str(data[s][j]) for s in series) + " |"
            for j, c in enumerate(cats)]
    md = f"# {title}\n\n" + "\n".join([header, sep] + rows)
    return {"image": f"images/{png.name}", "prompt": "\nImage Analysis:\n",
            "target": md, "kind": kind, "labelled": labelled, "index": idx}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12); ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "chart_data"))
    a = ap.parse_args()
    rng = random.Random(a.seed); out = Path(a.out)
    if out.exists(): shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    rows = [one_chart(rng, i, out / "images") for i in range(a.n)]
    (out / "data.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    import collections
    print(f"wrote {len(rows)} charts -> {out}",
          dict(collections.Counter(r['kind'] for r in rows)),
          f"labelled={sum(r['labelled'] for r in rows)}")

if __name__ == "__main__":
    main()
