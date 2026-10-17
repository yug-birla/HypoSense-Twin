"""Extract the blueprint .docx into grep-able Markdown (paragraphs + tables, document order).

The .docx remains the authoritative specification. The extracted Markdown exists so that
engineers and coding agents can search the specification without a Word renderer.
Figures are not extracted (see the .docx).

Usage:
    python -I scripts/extract_blueprint.py docs/HypoSense_Twin_v2_Blueprint.docx \
        docs/blueprint/HypoSense_Twin_v2_Blueprint.extracted.md

Standard library only, so it runs before the project environment exists.
"""

from __future__ import annotations

import hashlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _text(el: ET.Element) -> str:
    return "".join(t.text or "" for t in el.iter(W + "t"))


def _style(p: ET.Element) -> str:
    ppr = p.find(W + "pPr")
    if ppr is None:
        return ""
    s = ppr.find(W + "pStyle")
    if s is not None:
        return s.get(W + "val") or ""
    return "LIST" if ppr.find(W + "numPr") is not None else ""


def extract(docx: Path) -> str:
    with zipfile.ZipFile(docx) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    assert body is not None, "document.xml has no body"
    out: list[str] = []
    for el in body:
        if el.tag == W + "p":
            text, style = _text(el), _style(el)
            if not text.strip():
                continue
            low = style.lower()
            if low.startswith("heading") or low.startswith("title"):
                level = int(re.sub(r"\D", "", style) or "1")
                out.append("\n" + "#" * level + " " + text)
            elif style == "LIST" or "List" in style:
                out.append("- " + text)
            else:
                out.append(text)
        elif el.tag == W + "tbl":
            out.append("")
            for tr in el.iter(W + "tr"):
                cells = [
                    " / ".join(_text(p) for p in tc.iter(W + "p") if _text(p).strip())
                    for tc in tr.findall(W + "tc")
                ]
                out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
            out.append("")
    return "\n".join(out) + "\n"


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    header = (
        "<!-- MACHINE EXTRACTION of the blueprint .docx. The .docx is authoritative. -->\n"
        f"<!-- source: {src.as_posix()}  sha256: {digest} -->\n"
        "<!-- regenerate: python -I scripts/extract_blueprint.py <docx> <md> -->\n\n"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + extract(src), encoding="utf-8")
    print(f"wrote {dst} from {src} (sha256 {digest[:16]}...)")


if __name__ == "__main__":
    main()
