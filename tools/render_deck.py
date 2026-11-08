"""Render deck/northbay-resilience-deck.md (slides separated by '---') to a 16:9 HTML deck, then PDF with headless Chrome."""
import subprocess
import sys

SRC, HTML, PDF = "deck/northbay-resilience-deck.md", "deck/northbay-resilience-deck.html", "deck/northbay-resilience-deck.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: 13.333in 7.5in; margin: 0; }
body { margin: 0; font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #0b0b0b; }
.slide { width: 13.333in; height: 7.5in; box-sizing: border-box; padding: 0.55in 0.75in; page-break-after: always;
         position: relative; overflow: hidden; background: #fcfcfb; }
.slide::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 0.14in; background: #2a78d6; }
.slide.title { background: #0f2a4a; color: #fff; display: flex; flex-direction: column; justify-content: center; }
.slide.title::before { background: #eb6834; }
.slide.title h1 { font-size: 56px; line-height: 1.15; max-width: 10.5in; margin: 0 0 18px; }
.slide.title p { font-size: 24px; color: #d6e4f5; margin: 6px 0; }
h2 { font-size: 40px; margin: 0 0 22px; color: #0f2a4a; }
p, li { font-size: 25px; line-height: 1.45; }
li { margin: 4px 0; } ul ul li, ol ul li { font-size: 22px; }
table { border-collapse: collapse; width: 100%; font-size: 20px; margin: 6px 0 14px; }
th { text-align: left; background: #eef3fa; color: #52514e; padding: 8px 10px; border-bottom: 2px solid #c9d6e8; }
td { padding: 8px 10px; border-bottom: 1px solid #e3e2de; vertical-align: top; }
strong { color: #0f2a4a; } .slide.title strong { color: #fff; }
.footer { position: absolute; bottom: 0.25in; right: 0.6in; font-size: 12px; color: #77756f; }
"""


def md_to_html(md):
    return subprocess.run(["pandoc", "-f", "gfm-tex_math_dollars", "-t", "html"], input=md, capture_output=True, text=True,
                          check=True).stdout


slides = open(SRC).read().split("\n---\n")
parts = []
for i, s in enumerate(slides):
    cls = "slide title" if i == 0 else "slide"
    footer = "" if i == 0 else f'<div class="footer">NorthBay Resilience · {i + 1}/{len(slides)}</div>'
    parts.append(f'<section class="{cls}">{md_to_html(s)}{footer}</section>')
open(HTML, "w").write(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
                      + "".join(parts) + "</body></html>")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={PDF}",
                f"file://{__import__('os').path.abspath(HTML)}"], check=True, capture_output=True)
print("wrote", PDF)
