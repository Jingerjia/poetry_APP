from __future__ import annotations

import argparse
from pathlib import Path

import fitz


ROOT = Path(__file__).parent
DEFAULT_PDF_GLOB = "pdf/紅本新詩*藍本新詩*新歌頌詠.pdf"
DEFAULT_PDF_GLOB = "pdf/新詩.pdf"
DEFAULT_OUTPUT = "pdf_pages_130_266.txt"


def resolve_pdf(pattern: str) -> Path:
    matches = sorted(ROOT.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No PDF matched: {pattern}")
    if len(matches) > 1:
        matched = "\n".join(str(path) for path in matches)
        raise ValueError(f"Pattern matched more than one PDF:\n{matched}")
    return matches[0]


def extract_pages(pdf_path: Path, start_page: int, end_page: int) -> str:
    if start_page < 1 or end_page < start_page:
        raise ValueError("Page range must be 1-based and start_page <= end_page.")

    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        if end_page > doc.page_count:
            raise ValueError(
                f"Requested page {end_page}, but PDF has only {doc.page_count} pages."
            )

        for page_number in range(start_page, end_page + 1):
            text = doc[page_number - 1].get_text("text").strip()
            parts.append(f"===== Page {page_number} =====\n{text}")

    return "\n\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract text from a 1-based PDF page range with PyMuPDF."
    )
    parser.add_argument("--pdf", default=DEFAULT_PDF_GLOB, help="PDF path or glob pattern.")
    parser.add_argument("--start", type=int, default=130, help="First page, 1-based.")
    parser.add_argument("--end", type=int, default=266, help="Last page, 1-based.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output text file. Use '-' to print to stdout.",
    )
    args = parser.parse_args()

    pdf_path = resolve_pdf(args.pdf)
    text = extract_pages(pdf_path, args.start, args.end)

    if args.output == "-":
        print(text, end="")
        return

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.write_text(text, encoding="utf-8")
    print(f"Wrote {args.start}-{args.end} from {pdf_path} to {output_path}")


if __name__ == "__main__":
    main()
