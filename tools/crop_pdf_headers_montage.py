from __future__ import annotations

import argparse
import math
from pathlib import Path

import fitz
from PIL import Image


ROOT = Path(__file__).parent
DEFAULT_PDF_NAME = "\u7d05\u672c\u65b0\u8a69_\u85cd\u672c\u65b0\u8a69_\u65b0\u6b4c\u980c\u8a60.pdf"
DEFAULT_OUTPUT = "pdf_header_montage.png"


def resolve_pdf(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if path.exists():
        return path

    matches = sorted(ROOT.glob(value))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"No PDF matched: {value}")

    matched = "\n".join(str(match) for match in matches)
    raise ValueError(f"Pattern matched more than one PDF:\n{matched}")


def parse_pages(pages: str) -> list[int]:
    page_numbers: list[int] = []
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"Invalid page range: {part}")
            page_numbers.extend(range(start, end + 1))
        else:
            page_numbers.append(int(part))
    return page_numbers


def selected_pages(args: argparse.Namespace) -> list[int]:
    if args.pages:
        pages = parse_pages(args.pages)
    else:
        if args.end < args.start:
            raise ValueError("--end must be greater than or equal to --start")
        pages = list(range(args.start, args.end + 1))

    if not pages:
        raise ValueError("No pages selected.")
    return pages


def batches(values: list[int], size: int) -> list[list[int]]:
    if size < 1:
        raise ValueError("--batch-size must be greater than 0")
    return [values[index : index + size] for index in range(0, len(values), size)]


def render_header_crop(page: fitz.Page, zoom: float) -> Image.Image:
    page_rect = page.rect
    crop_width = page_rect.width * 4 / 9
    crop_height = page_rect.height / 10
    left = (page_rect.width - crop_width) / 2
    clip = fitz.Rect(left, 0, left + crop_width, crop_height)

    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def make_montage(images: list[Image.Image], columns: int, gap: int, background: str) -> Image.Image:
    tile_width = max(image.width for image in images)
    tile_height = max(image.height for image in images)
    rows = math.ceil(len(images) / columns)

    width = columns * tile_width + (columns - 1) * gap
    height = rows * tile_height + (rows - 1) * gap
    montage = Image.new("RGB", (width, height), background)

    for index, image in enumerate(images):
        row = index // columns
        column = index % columns
        x = column * (tile_width + gap) + (tile_width - image.width) // 2
        y = row * (tile_height + gap) + (tile_height - image.height) // 2
        montage.paste(image, (x, y))

    return montage


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render PDF pages with PyMuPDF, crop the top 1/10 height and centered "
            "4/9 width, then stitch every batch of crops into one image."
        )
    )
    parser.add_argument("--pdf", default=f"pdf/{DEFAULT_PDF_NAME}", help="PDF path or glob.")
    parser.add_argument("--start", type=int, default=130, help="First page, 1-based.")
    parser.add_argument("--end", type=int, default=266, help="Last page, 1-based.")
    parser.add_argument("--pages", help="Specific pages, e.g. 130,132,140-150.")
    parser.add_argument("--batch-size", type=int, default=30, help="Images per montage.")
    parser.add_argument("--columns", type=int, default=5, help="Number of montage columns.")
    parser.add_argument("--gap", type=int, default=12, help="Pixels between crops.")
    parser.add_argument("--zoom", type=float, default=2.0, help="Render scale.")
    parser.add_argument("--background", default="white", help="Montage background color.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output PNG path.")
    args = parser.parse_args()

    pages = selected_pages(args)
    pdf_path = resolve_pdf(args.pdf)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    with fitz.open(pdf_path) as doc:
        for page_batch in batches(pages, args.batch_size):
            images: list[Image.Image] = []
            for page_number in page_batch:
                if page_number < 1 or page_number > doc.page_count:
                    raise ValueError(
                        f"Requested page {page_number}, but PDF has {doc.page_count} pages."
                    )
                images.append(render_header_crop(doc[page_number - 1], args.zoom))

            first_page = page_batch[0]
            last_page = page_batch[-1]
            batch_output_path = output_path.with_name(
                f"{output_path.stem}_{first_page}_{last_page}{output_path.suffix}"
            )

            montage = make_montage(images, args.columns, args.gap, args.background)
            montage.save(batch_output_path)
            written_paths.append(batch_output_path)
            print(
                f"Wrote {len(images)} crops from pages "
                f"{first_page}-{last_page} to {batch_output_path}"
            )

    print(f"Done. Wrote {len(written_paths)} montage files.")


if __name__ == "__main__":
    main()
