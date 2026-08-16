#!/usr/bin/env python3
"""Render docs/paper/report.md to a standalone HTML report + PDF.

The PDF is produced by headless Edge (or Chrome) print-to-pdf, so it needs no
network. Figures are inlined as base64 data URIs so both outputs are fully
standalone.
"""
from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path

import markdown
import shutil

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "paper" / "report.md"
FIG = ROOT / "docs" / "paper" / "figures"
OUT_HTML = ROOT / "docs" / "paper" / "report.html"
OUT_PDF = ROOT / "docs" / "paper" / "report.pdf"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
] + [shutil.which(n) for n in
     ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
      "microsoft-edge", "msedge") if shutil.which(n)]

CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; max-width: 900px; margin: 0 auto;
       padding: 42px 28px 80px; color: #1c2733; line-height: 1.65; background: #fff; }
h1 { font-size: 26px; border-bottom: 3px solid #0e5a8a; padding-bottom: 10px; }
h2 { font-size: 19px; margin-top: 34px; color: #0e5a8a; }
h3 { font-size: 15px; margin-top: 24px; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 13.5px; }
th, td { border: 1px solid #e3e9f0; padding: 7px 10px; text-align: left; }
th { background: #f2f6fa; }
img { max-width: 100%; border: 1px solid #e3e9f0; border-radius: 8px; margin: 10px 0; }
blockquote { border-left: 4px solid #0e5a8a; margin: 14px 0; padding: 4px 16px; background: #f2f6fa; }
code { background: #f2f6fa; padding: 2px 5px; border-radius: 4px; font-size: 13px; }
@media print {
  body { padding: 0 4mm; }
  img { page-break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
"""


def embed_figures(html: str) -> str:
    def repl(m: re.Match) -> str:
        cap, fname = m.group(1), m.group(2)
        path = FIG / fname
        if not path.is_file():
            return m.group(0)
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'<figure><img alt="{cap}" src="data:image/png;base64,{b64}"/>' \
               f'<figcaption>{cap}</figcaption></figure>'

    return re.sub(
        r'<img alt="([^"]*)" src="(?:figures/|\.\./figures/)(fig\d+_\w+\.png)"\s*/?>',
        repl,
        html,
    )


def main():
    html = markdown.markdown(MD.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    html = embed_figures(html)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SimLeap Technical Report</title>
<style>{CSS}</style></head><body>
{html}
</body></html>"""
    OUT_HTML.write_text(doc, encoding="utf-8")
    print(f"[paper] wrote {OUT_HTML}")

    edge = next((p for p in EDGE_CANDIDATES if Path(p).is_file()), None)
    if edge is None:
        print("[paper] no Edge/Chrome found; PDF skipped (HTML is standalone).")
        return 0
    cmd = [
        edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri(),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if OUT_PDF.is_file():
        print(f"[paper] PDF -> {OUT_PDF} ({OUT_PDF.stat().st_size} bytes)")
        return 0
    print("[paper] PDF failed; HTML remains usable.")
    print(proc.stderr[-500:] if proc.stderr else "")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
