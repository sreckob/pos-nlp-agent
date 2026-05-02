"""
Receipt Generator
=================
Generates realistic POS receipt PNG images for dispute demo scenarios.
Each receipt matches a real transaction in the database.

Usage:
    pip install Pillow
    python generate_receipts.py

Output:
    receipts/receipt_dispute_01_maxi.png
    receipts/receipt_dispute_02_nis_petrol.png
    receipts/receipt_dispute_03_gigatron.png

These receipts correspond to the demo transactions created by demo_seed.py:
  DISPUTE-01: Visa ****4242 — 3,240.50 RSD at Maxi Supermarket
  DISPUTE-02: Mastercard ****5555 — 5,870.00 RSD at NIS Petrol
  DISPUTE-03: Dinacard ****1111 — 42,500.00 RSD at Gigatron
"""

import os
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ── Output directory ──────────────────────────────────────────
OUTPUT_DIR = "receipts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Receipt data matching demo_seed.py transactions ───────────
RECEIPTS = [
    {
        "filename":      "receipt_dispute_01_maxi.png",
        "merchant":      "MAXI SUPERMARKET",
        "address":       "Bulevar Kralja Aleksandra 284",
        "city":          "Beograd 11000",
        "terminal_id":   "T00101",
        "merchant_id":   "M001",
        "date":          "28.04.2026",
        "time":          "14:22:10",
        "card_brand":    "VISA",
        "pan_masked":    "411111******4242",
        "card_type":     "CONTACTLESS",
        "amount":        "3.240,50",
        "currency":      "RSD",
        "approval_code": "DM0001",
        "response_code": "00",
        "status":        "APPROVED",
        "tx_type":       "PURCHASE",
        "note":          "* ORIGINAL CHARGE *",
    },
    {
        "filename":      "receipt_dispute_02_nis_petrol.png",
        "merchant":      "NIS PETROL",
        "address":       "Autoput za Novi Sad bb",
        "city":          "Beograd 11080",
        "terminal_id":   "T00801",
        "merchant_id":   "M008",
        "date":          "27.04.2026",
        "time":          "09:15:00",
        "card_brand":    "MASTERCARD",
        "pan_masked":    "510000******5555",
        "card_type":     "CHIP",
        "amount":        "5.870,00",
        "currency":      "RSD",
        "approval_code": "DN0001",
        "response_code": "00",
        "status":        "APPROVED",
        "tx_type":       "PURCHASE",
        "note":          "* ORIGINAL CHARGE *",
    },
    {
        "filename":      "receipt_dispute_03_gigatron.png",
        "merchant":      "GIGATRON",
        "address":       "Trg Republike 5",
        "city":          "Beograd 11000",
        "terminal_id":   "T02001",
        "merchant_id":   "M020",
        "date":          "22.04.2026",
        "time":          "16:45:00",
        "card_brand":    "DINACARD",
        "pan_masked":    "989100******1111",
        "card_type":     "CHIP",
        "amount":        "42.500,00",
        "currency":      "RSD",
        "approval_code": "DG0001",
        "response_code": "00",
        "status":        "APPROVED",
        "tx_type":       "KUPOVINA",
        "note":          "* ORIGINAL CHARGE *",
    },
]

# ── Layout constants ──────────────────────────────────────────
WIDTH       = 380
BG_COLOR    = (255, 255, 255)
TEXT_COLOR  = (20, 20, 20)
GRAY_COLOR  = (120, 120, 120)
LINE_COLOR  = (200, 200, 200)
GREEN_COLOR = (22, 163, 74)
RED_COLOR   = (220, 38, 38)

def load_font(size: int, bold: bool = False):
    """Load a system font or fall back to default."""
    try:
        if bold:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except:
            return ImageFont.load_default()

def draw_dashed_line(draw, y, width, margin=20):
    """Draw a dashed horizontal line."""
    x = margin
    while x < width - margin:
        draw.line([(x, y), (min(x + 8, width - margin), y)], fill=LINE_COLOR, width=1)
        x += 14

def center_text(draw, text, y, width, font, color=TEXT_COLOR):
    """Draw centered text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    draw.text((x, y), text, font=font, fill=color)
    return bbox[3] - bbox[1]

def left_right_text(draw, left, right, y, width, font,
                    left_color=GRAY_COLOR, right_color=TEXT_COLOR, margin=24):
    """Draw left-aligned label and right-aligned value on same line."""
    draw.text((margin, y), left, font=font, fill=left_color)
    bbox = draw.textbbox((0, 0), right, font=font)
    rw = bbox[2] - bbox[0]
    draw.text((width - margin - rw, y), right, font=font, fill=right_color)

def generate_receipt(data: dict):
    """Generate a single receipt PNG."""

    # ── Estimate height ───────────────────────────────────────
    height = 640
    img    = Image.new("RGB", (WIDTH, height), BG_COLOR)
    draw   = ImageDraw.Draw(img)

    # Fonts
    f_large  = load_font(20, bold=True)
    f_medium = load_font(14)
    f_small  = load_font(11)
    f_tiny   = load_font(10)

    y = 24

    # ── Header ────────────────────────────────────────────────
    center_text(draw, data["merchant"], y, WIDTH, f_large)
    y += 28
    center_text(draw, data["address"], y, WIDTH, f_small, GRAY_COLOR)
    y += 16
    center_text(draw, data["city"], y, WIDTH, f_small, GRAY_COLOR)
    y += 24

    draw_dashed_line(draw, y, WIDTH)
    y += 12

    # ── Terminal info ─────────────────────────────────────────
    left_right_text(draw, "Terminal ID:", data["terminal_id"], y, WIDTH, f_small)
    y += 18
    left_right_text(draw, "Merchant ID:", data["merchant_id"], y, WIDTH, f_small)
    y += 18
    left_right_text(draw, "Date:", data["date"], y, WIDTH, f_small)
    y += 18
    left_right_text(draw, "Time:", data["time"], y, WIDTH, f_small)
    y += 24

    draw_dashed_line(draw, y, WIDTH)
    y += 14

    # ── Transaction type ──────────────────────────────────────
    center_text(draw, data["tx_type"], y, WIDTH, f_medium)
    y += 24

    draw_dashed_line(draw, y, WIDTH)
    y += 14

    # ── Card info ─────────────────────────────────────────────
    left_right_text(draw, "Card brand:", data["card_brand"], y, WIDTH, f_small)
    y += 18
    left_right_text(draw, "Card number:", data["pan_masked"], y, WIDTH, f_small)
    y += 18
    left_right_text(draw, "Entry mode:", data["card_type"], y, WIDTH, f_small)
    y += 24

    draw_dashed_line(draw, y, WIDTH)
    y += 14

    # ── Amount — large and prominent ─────────────────────────
    amount_str = f"{data['amount']} {data['currency']}"
    center_text(draw, "AMOUNT", y, WIDTH, f_small, GRAY_COLOR)
    y += 16
    center_text(draw, amount_str, y, WIDTH, f_large)
    y += 32

    draw_dashed_line(draw, y, WIDTH)
    y += 14

    # ── Authorization ─────────────────────────────────────────
    left_right_text(draw, "Auth code:", data["approval_code"], y, WIDTH, f_small)
    y += 18
    left_right_text(draw, "Response:", data["response_code"], y, WIDTH, f_small)
    y += 18

    # Status badge
    status_color = GREEN_COLOR if data["status"] == "APPROVED" else RED_COLOR
    center_text(draw, f"● {data['status']}", y, WIDTH, f_medium, status_color)
    y += 28

    draw_dashed_line(draw, y, WIDTH)
    y += 14

    # ── Note ──────────────────────────────────────────────────
    center_text(draw, data["note"], y, WIDTH, f_small, GRAY_COLOR)
    y += 18

    center_text(draw, "KEEP THIS RECEIPT", y, WIDTH, f_small, GRAY_COLOR)
    y += 18

    center_text(draw, "Hvala na kupovini!", y, WIDTH, f_small, GRAY_COLOR)
    y += 24

    draw_dashed_line(draw, y, WIDTH)
    y += 16

    # ── Footer ────────────────────────────────────────────────
    center_text(draw, "Powered by NBS Payment System", y, WIDTH, f_tiny, LINE_COLOR)
    y += 14
    center_text(draw, "www.nbs.rs", y, WIDTH, f_tiny, LINE_COLOR)
    y += 20

    # ── Crop to actual content height ────────────────────────
    img_cropped = img.crop((0, 0, WIDTH, y + 10))

    # Add subtle border
    bordered = Image.new("RGB", (WIDTH + 4, y + 14), LINE_COLOR)
    bordered.paste(img_cropped, (2, 2))

    # Save
    path = os.path.join(OUTPUT_DIR, data["filename"])
    bordered.save(path, "PNG", dpi=(200, 200))
    print(f"  ✓ {path}")
    return path


def main():
    print(f"Generating {len(RECEIPTS)} receipt images...")
    print(f"Output directory: {OUTPUT_DIR}/\n")

    for receipt_data in RECEIPTS:
        generate_receipt(receipt_data)

    print(f"\nDone. Upload these during dispute demo scenarios:")
    print(f"  Dispute 1 — Visa ****4242 at Maxi:        receipt_dispute_01_maxi.png")
    print(f"  Dispute 2 — MC ****5555 at NIS Petrol:    receipt_dispute_02_nis_petrol.png")
    print(f"  Dispute 3 — Dinacard ****1111 at Gigatron: receipt_dispute_03_gigatron.png")


if __name__ == "__main__":
    main()
