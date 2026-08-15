#!/usr/bin/env python3
"""Render docs/paper/report.md to a standalone HTML report."""
from __future__ import annotations

from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "paper" / "report.md"
OUT = ROOT / "docs" / "paper" / "report.html"

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
"""


def main():
    html = markdown.markdown(MD.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SimLeap Technical Report</title>
<style>{CSS}</style></head><body>
{html}
</body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"[paper] wrote {OUT}")


if __name__ == "__main__":
    main()
