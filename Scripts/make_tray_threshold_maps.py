#!/usr/bin/env python3
"""Create pixel-level threshold atlases in recorded tray coordinates.

This script is intentionally separate from make_wafer_threshold_maps.py.
April and July chip-to-wafer locations are not recoverable from the available
records, so these outputs are tray-coordinate atlases, never wafer maps.

Display convention follows the supplied Die Picking Rule PDF: A/B/C run from
top to bottom, columns 1..8 run from left to right, and A1 is upper-left. The
tray is physically rotated 180 degrees when loaded into the ATE; logical slot
IDs are retained here. Missing/unusable data and nonpositive/nonfinite pixels
are black. Positive finite thresholds use 256 yellow lightness levels.

Inputs are read only. Every run creates a new timestamped output directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_BATCHES = ("testdata_260416", "testdata_260714")
RUN_PATTERN = re.compile(r"^\d{8}-\d{6}$")
SLOT_PATTERN = re.compile(r"^(?P<group>.+)_(?P<slot>[ABC][1-8])$")
APRIL_ID_PATTERN = re.compile(r"^(51PK417B)([ABC][1-8])$")
ROWS = "ABC"
COLS = tuple(range(1, 9))
BLACK = (0, 0, 0)
LIGHTNESS_RANGE = (0.95, 0.125)
_lightness = np.linspace(*LIGHTNESS_RANGE, 256)
_yellow = np.minimum(1.0, 2.0 * _lightness)
_blue = np.maximum(0.0, 2.0 * _lightness - 1.0)
COLOR_LUT = np.rint(
    255 * np.column_stack((_yellow, _yellow, _blue))
).astype(np.uint8)

TILE_SIZE = (512, 1024)
TILE_ORIGIN = (200, 330)
CANVAS_SIZE = (4496, 3780)


def font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_chip_id(batch: str, raw_chip_id: str) -> str:
    if batch == "testdata_260416":
        return APRIL_ID_PATTERN.sub(r"\1_\2", raw_chip_id)
    return raw_chip_id


def slot_row_col(slot: str) -> tuple[int, int]:
    return ROWS.index(slot[0]), int(slot[1:]) - 1


def tile_origin(slot: str) -> tuple[int, int]:
    row, col = slot_row_col(slot)
    return (
        TILE_ORIGIN[0] + col * TILE_SIZE[0],
        TILE_ORIGIN[1] + row * TILE_SIZE[1],
    )


def discover_batch(root: Path, batch: str):
    """Support the standard and April ATE-export folder layouts."""
    records = []
    seen_runs = set()

    def add(outer: Path, chip: Path, run: Path, source_layout: str):
        resolved = run.resolve()
        if resolved in seen_runs:
            return
        seen_runs.add(resolved)
        raw = chip.name
        corrected = normalize_chip_id(batch, raw)
        match = SLOT_PATTERN.fullmatch(corrected)
        if not match:
            raise ValueError(f"Unexpected chip ID in {batch}: {raw} ({run})")
        records.append(
            dict(
                batch=batch,
                chip_id=corrected,
                raw_chip_id=raw,
                chip_id_normalized=(corrected != raw),
                group=match.group("group"),
                slot=match.group("slot"),
                outer=outer.name,
                run_time=run.name,
                run_path=str(run),
                source_layout=source_layout,
            )
        )

    for outer in sorted(path for path in root.iterdir() if path.is_dir()):
        for chip in sorted(path for path in outer.iterdir() if path.is_dir()):
            for run in sorted(path for path in chip.iterdir() if path.is_dir()):
                if RUN_PATTERN.fullmatch(run.name):
                    add(outer, chip, run, "standard")

        chips_root = outer / "CHDO" / "Chips"
        if not chips_root.is_dir():
            continue
        for lot in sorted(path for path in chips_root.iterdir() if path.is_dir()):
            for chip in sorted(path for path in lot.iterdir() if path.is_dir()):
                cern_pc = chip / "CERN_PC"
                if not cern_pc.is_dir():
                    continue
                for run in sorted(path for path in cern_pc.iterdir() if path.is_dir()):
                    if RUN_PATTERN.fullmatch(run.name):
                        add(outer, chip, run, "ate_export")

    if not records:
        raise ValueError(f"No test runs found in {root}")

    latest = {}
    for record in sorted(
        records,
        key=lambda item: (item["run_time"], item["outer"], item["run_path"]),
    ):
        latest[record["chip_id"]] = record
    return latest, len(records)


def load_map(record: dict):
    run = Path(record["run_path"])
    analyse = run / "analyse_output.json"
    contact = run / "CONTACT_FAIL"
    if analyse.is_file():
        try:
            json.loads(analyse.read_text())
            record["run_status"] = "ANALYZED"
        except (OSError, ValueError):
            record["run_status"] = "INVALID_ANALYSE_OUTPUT"
    elif contact.is_file():
        record["run_status"] = "CONTACT_FAIL"
    else:
        record["run_status"] = "NO_ANALYSE_OUTPUT"

    path = run / "Threshold_Scan_Queue" / "thrmap.npy"
    record["map_path"] = str(path)
    if record["run_status"] == "CONTACT_FAIL":
        record["map_status"] = "CONTACT_FAIL"
        return None
    if not path.is_file():
        record["map_status"] = "MISSING_MAP"
        return None
    try:
        array = np.load(path, allow_pickle=False)
        if array.shape != (512, 1024) or array.dtype.kind not in "fiu":
            raise ValueError(
                f"Expected numeric (512,1024), found {array.shape} {array.dtype}"
            )
        record["map_status"] = "AVAILABLE"
        record["source_sha256"] = sha256(path)
        record["pixels_total"] = int(array.size)
        record["pixels_zero"] = int(np.count_nonzero(array == 0))
        record["pixels_negative_or_nonfinite"] = int(
            np.count_nonzero((array < 0) | ~np.isfinite(array))
        )
        positive = array[np.isfinite(array) & (array > 0)]
        record["pixels_positive_finite"] = int(positive.size)
        record["positive_median_dac"] = (
            float(np.median(positive)) if positive.size else None
        )
        return array
    except (OSError, ValueError, EOFError) as exc:
        record["map_status"] = "INVALID_MAP"
        record["error"] = str(exc)
        return None


def orient(array, rotation: int, flip_x: bool, flip_y: bool):
    if flip_x:
        array = np.fliplr(array)
    if flip_y:
        array = np.flipud(array)
    return np.rot90(array, rotation // 90)


def threshold_rgb(fraction):
    index = np.rint(np.clip(fraction, 0, 1) * 255).astype(np.uint8)
    return COLOR_LUT[index]


def colorize(array, low: float, high: float):
    positive = np.isfinite(array) & (array > 0)
    safe = np.where(positive, array, low)
    rgb = threshold_rgb((safe - low) / (high - low))
    rgb[~positive] = BLACK
    return Image.fromarray(rgb)


def preview(canvas):
    result = canvas.copy()
    result.thumbnail((1500, 1300), Image.Resampling.LANCZOS)
    scale = result.width / canvas.width
    x0, y0 = TILE_ORIGIN
    box = (x0, y0, x0 + 8 * TILE_SIZE[0], y0 + 3 * TILE_SIZE[1])
    target = tuple(round(value * scale) for value in box)
    data = canvas.crop(box).resize(
        (target[2] - target[0], target[3] - target[1]),
        Image.Resampling.NEAREST,
    )
    result.paste(data, (target[0], target[1]))
    return result


def batch_note(batch: str) -> str:
    if batch == "testdata_260416":
        return "April: recorded group labels do not establish wafer membership or die location"
    return "July: T/B/E are recorded group labels; E meaning and wafer die locations are not assumed"


def render_group(batch, group, group_records, args, output):
    canvas = Image.new("RGB", CANVAS_SIZE, "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (120, 45),
        f"{batch} | {group} | pixel-level Threshold atlas",
        font=font(58),
        fill="black",
    )
    draw.text(
        (120, 122),
        "TRAY COORDINATES - NOT A WAFER MAP",
        font=font(39),
        fill=(155, 42, 38),
    )
    draw.text(
        (120, 180),
        "PDF view: A1 upper-left; A/B/C top-to-bottom; 1-8 left-to-right",
        font=font(29),
        fill="black",
    )
    draw.text((120, 225), batch_note(batch), font=font(26), fill="black")
    draw.text(
        (120, 267),
        f"latest run per normalized chip ID | within-chip display: {args.rotation} deg CCW",
        font=font(25),
        fill="black",
    )

    output_records = []
    by_slot = {record["slot"]: record for record in group_records}
    for row in ROWS:
        for col in COLS:
            slot = f"{row}{col}"
            x, y = tile_origin(slot)
            if slot not in by_slot:
                record = dict(
                    batch=batch,
                    group=group,
                    slot=slot,
                    chip_id=f"{group}_{slot}",
                    map_status="UNRECORDED_SLOT",
                )
                draw.rectangle((x, y, x + 511, y + 1023), fill=BLACK)
            else:
                record = dict(by_slot[slot])
                array = load_map(record)
                if array is None:
                    draw.rectangle((x, y, x + 511, y + 1023), fill=BLACK)
                else:
                    positive = np.isfinite(array) & (array > 0)
                    record["pixels_below_color_min"] = int(
                        np.count_nonzero(positive & (array < args.vmin))
                    )
                    record["pixels_above_color_max"] = int(
                        np.count_nonzero(positive & (array > args.vmax))
                    )
                    tile = colorize(
                        orient(array, args.rotation, args.flip_x, args.flip_y),
                        args.vmin,
                        args.vmax,
                    )
                    canvas.paste(tile, (x, y))
            record["tray_row_col"] = list(slot_row_col(slot))
            record["image_tile_xy"] = [x, y]
            output_records.append(record)

    counts = Counter(item["map_status"] for item in output_records)
    draw.text(
        (120, 3430),
        " | ".join(f"{key}: {value}" for key, value in counts.items()),
        font=font(26),
        fill="black",
    )
    bar = threshold_rgb(np.tile(np.linspace(0, 1, 980), (34, 1)))
    canvas.paste(Image.fromarray(bar), (120, 3480))
    draw.text(
        (120, 3520),
        f"{args.vmin:g} DAC (light)                         {args.vmax:g} DAC (dark)",
        font=font(24),
        fill="black",
    )
    draw.rectangle((1260, 3480, 1310, 3514), fill=BLACK)
    draw.text(
        (1330, 3480),
        "No usable threshold / unrecorded slot",
        font=font(25),
        fill="black",
    )
    draw.text(
        (120, 3580),
        "256 yellow levels; black states remain distinct in manifest.json",
        font=font(25),
        fill="black",
    )
    draw.text(
        (120, 3630),
        "ATE physical loading is rotated 180 deg; this display retains logical tray IDs",
        font=font(25),
        fill="black",
    )

    safe_group = re.sub(r"[^A-Za-z0-9_.-]+", "_", group)
    full_path = output / f"{safe_group}_threshold_full.png"
    preview_path = output / f"{safe_group}_threshold_preview.png"
    canvas.save(full_path)
    small = preview(canvas)
    small.save(preview_path)
    return output_records, small


def render_reference(batch, group, recorded_slots, output):
    canvas = Image.new("RGB", CANVAS_SIZE, "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (120, 45),
        f"{batch} | {group} | recorded chip ID reference",
        font=font(58),
        fill="black",
    )
    draw.text(
        (120, 125),
        "Logical tray view: A1 upper-left; A/B/C top-to-bottom; 1-8 left-to-right",
        font=font(30),
        fill="black",
    )
    for row in ROWS:
        for col in COLS:
            slot = f"{row}{col}"
            x, y = tile_origin(slot)
            recorded = slot in recorded_slots
            fill = (229, 240, 255) if recorded else (225, 225, 225)
            outline = (72, 104, 143) if recorded else (135, 135, 135)
            draw.rectangle((x, y, x + 511, y + 1023), fill=fill, outline=outline, width=5)
            cx, cy = x + 256, y + 512
            draw.text((cx, cy - 70), slot, font=font(76), fill=outline, anchor="mm")
            label = f"{group}_{slot}" if recorded else "not recorded"
            draw.text((cx, cy + 65), label, font=font(31), fill=outline, anchor="mm")
    draw.text(
        (120, 3490),
        "Reference only: these positions do not identify physical wafer die coordinates",
        font=font(28),
        fill="black",
    )
    safe_group = re.sub(r"[^A-Za-z0-9_.-]+", "_", group)
    canvas.save(output / f"{safe_group}_chip_id_reference.png")
    canvas.thumbnail((1500, 1300), Image.Resampling.LANCZOS)
    canvas.save(output / f"{safe_group}_chip_id_reference_preview.png")


def make_overview(images, output_path: Path):
    if not images:
        return
    width, height = 1500, 1300
    cols = 2
    rows = (len(images) + cols - 1) // cols
    overview = Image.new("RGB", (cols * width, rows * height), "white")
    for index, image in enumerate(images):
        overview.paste(image, ((index % cols) * width, (index // cols) * height))
    overview.save(output_path)


def self_test():
    assert slot_row_col("A1") == (0, 0)
    assert slot_row_col("C8") == (2, 7)
    assert tile_origin("A1") == TILE_ORIGIN
    assert tile_origin("C8") == (
        TILE_ORIGIN[0] + 7 * 512,
        TILE_ORIGIN[1] + 2 * 1024,
    )
    assert normalize_chip_id("testdata_260416", "51PK417BA1") == "51PK417B_A1"
    assert normalize_chip_id("testdata_260714", "0RUZS08T_A1") == "0RUZS08T_A1"
    array = np.arange(512 * 1024).reshape(512, 1024)
    assert orient(array, 90, False, False).shape == (1024, 512)
    palette = threshold_rgb(np.linspace(0, 1, 256))
    assert np.array_equal(palette, COLOR_LUT)
    assert len(np.unique(palette, axis=0)) == 256
    assert all(tuple(color) != BLACK for color in palette)
    test = np.asarray(colorize(np.array([[0.0, -1.0, np.nan, 5.0]]), 0, 15))
    assert np.all(test[0, :3] == 0)
    print("Self-test: tray coordinates, April ID normalization, orientation and colors OK")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--batch",
        action="append",
        choices=DEFAULT_BATCHES,
        help="Repeat to select batches; default is April and July",
    )
    parser.add_argument("--vmin", type=float, default=0.0)
    parser.add_argument("--vmax", type=float, default=15.0)
    parser.add_argument("--rotation", type=int, choices=(90, 270), default=90)
    parser.add_argument("--flip-x", action="store_true")
    parser.add_argument("--flip-y", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    self_test()
    if args.self_test:
        return
    if not np.isfinite([args.vmin, args.vmax]).all() or args.vmin >= args.vmax:
        parser.error("Require finite vmin < vmax")

    batches = args.batch or list(DEFAULT_BATCHES)
    output_root = args.output_root or (
        args.project_root / "Results" / "TrayThresholdMaps"
    )
    output = output_root / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output.mkdir(parents=True, exist_ok=False)
    manifest_batches = {}
    all_previews = []

    for batch in batches:
        root = args.project_root.resolve() / "testdata" / batch
        latest, run_count = discover_batch(root, batch)
        batch_output = output / batch
        batch_output.mkdir()
        by_group = defaultdict(list)
        for record in latest.values():
            by_group[record["group"]].append(record)

        batch_records = []
        batch_previews = []
        for group in sorted(by_group):
            records, small = render_group(
                batch, group, by_group[group], args, batch_output
            )
            render_reference(
                batch,
                group,
                {record["slot"] for record in by_group[group]},
                batch_output,
            )
            batch_records.extend(records)
            batch_previews.append(small)
            all_previews.append(small)
            print(group, dict(Counter(r["map_status"] for r in records)), flush=True)
        make_overview(batch_previews, batch_output / "all_groups_overview.png")
        manifest_batches[batch] = dict(
            input_root=str(root),
            run_count=run_count,
            unique_normalized_chip_count=len(latest),
            groups=sorted(by_group),
            note=batch_note(batch),
            records=batch_records,
        )

    make_overview(all_previews, output / "april_july_all_groups_overview.png")
    manifest = dict(
        artifact="tray-coordinate pixel-level threshold atlas; not a wafer map",
        tray_coordinates="PDF view: A1 upper-left; A/B/C top-to-bottom; 1..8 left-to-right",
        ate_loading="physically rotated 180 degrees; logical tray IDs retained",
        wafer_location_status="unavailable for April and July; no physical die position is inferred",
        selection="latest run per batch-scoped normalized chip ID; no fallback to older successful run",
        color_range_dac=[args.vmin, args.vmax],
        color_levels=256,
        hls_lightness_range=list(LIGHTNESS_RANGE),
        pixel_policy="positive finite threshold values yellow; zero, negative, nonfinite, missing maps, contact failures and unrecorded slots black; states retained per record",
        orientation=dict(
            rotation_ccw=args.rotation,
            flip_source_x=args.flip_x,
            flip_source_y=args.flip_y,
            interpretation="display only; not used for physical direction",
        ),
        batches=manifest_batches,
    )
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    )
    print(f"OUTPUT: {output}", flush=True)


if __name__ == "__main__":
    main()
