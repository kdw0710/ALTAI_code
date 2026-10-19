#!/usr/bin/env python3
"""Create March ALTAI PowerTest maps focused on subtle spatial trends.

Run: python3 make_wafer_power_trend_maps.py
Dependencies: numpy, Pillow. Inputs are read only.
Outputs: Results/WaferPowerTrendMaps/<unique timestamp>/ (never overwritten).

Only values inside the selected normal-detail window are assigned yellow
lightness levels. Measured values outside that window are gray; missing,
invalid and CONTACT_FAIL entries are black. The script also calculates the
mean and sample standard deviation at each common die position across the
seven wafers and the correlation between schematic radial position and current.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from make_wafer_threshold_maps import (
    BATCH,
    BLACK,
    CANVAS_SIZE,
    POSITIONS,
    PROJECT,
    SLOTS,
    TILE_SIZE,
    data_preview,
    discover,
    font,
    render_id_reference,
    threshold_rgb,
    tile_origin,
)
from make_wafer_power_maps import PARAMETERS, load_power_values


TREND_RANGES = {'i_a': (11.5, 14.2), 'i_d': (42.0, 46.0)}
STD_RANGES = {'i_a': (0.0, 1.5), 'i_d': (0.0, 1.5)}
EXCLUDED = (92, 92, 92)
INSUFFICIENT = (155, 155, 155)
POINT_COLOR = (226, 178, 0)
FIT_COLOR = (190, 25, 25)


def collect_records(project_root):
    root = project_root.resolve() / 'testdata' / BATCH
    latest, run_count = discover(root)
    records = {}
    for chip, source in latest.items():
        record = dict(source)
        values = load_power_values(record)
        record.update(values)
        slot = chip[7:]
        die = SLOTS[slot]
        row, col = POSITIONS[die]
        record.update(
            die_number=die,
            slot=slot,
            wafer=chip[:7],
            wafer_grid_row=row,
            wafer_grid_col=col,
        )
        records[chip] = record
    return root, latest, run_count, records


def yellow_color(value, low, high):
    fraction = np.clip((value - low) / (high - low), 0, 1)
    return tuple(int(channel) for channel in threshold_rgb(np.array(fraction)))


def tile_rect(row, col):
    x, y = tile_origin(row, col)
    return x, y, x + TILE_SIZE[0] - 1, y + TILE_SIZE[1] - 1


def draw_wafer_frame(draw, title, subtitle):
    draw.text((180, 65), title, font=font(67), fill='black')
    draw.text(
        (180, 158),
        'PDF tray coordinates: A1 upper-left; A/B/C top-to-bottom; 1-8 left-to-right',
        font=font(36), fill='black',
    )
    draw.text((180, 214), subtitle, font=font(32), fill='black')
    draw.text(
        (180, 264),
        f'{BATCH} | latest run per corrected chip ID | schematic die positions',
        font=font(30), fill='black',
    )
    draw.ellipse((55, 300, 6545, 6840), outline=(160, 160, 160), width=5)
    draw.polygon([(3260, 6838), (3340, 6838), (3300, 6800)], fill='black')


def draw_legend(draw, canvas, low, high, unit, counts, extra='', gray_label='measured but outside trend window'):
    draw.text(
        (180, 6885), ' | '.join(f'{key}: {value}' for key, value in counts.items()),
        font=font(31), fill='black',
    )
    bar = threshold_rgb(np.tile(np.linspace(0, 1, 1100), (42, 1)))
    canvas.paste(Image.fromarray(bar), (180, 6955))
    draw.text(
        (180, 7005), f'{low:g} {unit} (light)                         {high:g} {unit} (dark)',
        font=font(30), fill='black',
    )
    draw.rectangle((1580, 6955, 1635, 6997), fill=EXCLUDED)
    draw.text((1660, 6955), gray_label, font=font(30), fill='black')
    draw.rectangle((3240, 6955, 3295, 6997), fill=BLACK)
    draw.text((3320, 6955), 'missing / contact fail / invalid', font=font(30), fill='black')
    draw.text(
        (180, 7070),
        'The yellow scale is intentionally narrow and is for spatial-trend inspection, not pass/fail grading.',
        font=font(31), fill='black',
    )
    draw.text((180, 7130), extra, font=font(29), fill='black')
    draw.text(
        (180, 7180), 'Chip IDs: see chip_id_reference.png. No missing value is interpolated.',
        font=font(30), fill='black',
    )


def render_wafer(wafer, name, records, value_range, output):
    low, high = value_range
    spec = PARAMETERS[name]
    canvas = Image.new('RGB', CANVAS_SIZE, 'white')
    draw = ImageDraw.Draw(canvas)
    draw_wafer_frame(
        draw,
        f'ALTAI {wafer} | {spec["title"]} trend-detail map',
        f'Normal-detail window: {low:g}-{high:g} mA; outside-window measurements are excluded from the yellow scale',
    )
    counts = Counter()
    for slot, die in sorted(SLOTS.items(), key=lambda item: item[1]):
        chip = f'{wafer}{slot}'
        row, col = POSITIONS[die]
        record = records.get(chip)
        if record is None or record.get(name) is None:
            draw.rectangle(tile_rect(row, col), fill=BLACK)
            key = 'MISSING_CHIP' if record is None else record['power_status']
            counts[key] += 1
            continue
        value = record[name]
        if low <= value <= high:
            draw.rectangle(tile_rect(row, col), fill=yellow_color(value, low, high))
            counts['IN_TREND_WINDOW'] += 1
        else:
            draw.rectangle(tile_rect(row, col), fill=EXCLUDED)
            counts['EXCLUDED_MEASURED'] += 1
    draw_legend(
        draw, canvas, low, high, 'mA', counts,
        'Each die contains one scalar current value; yellow does not represent individual pixels.',
    )
    full = output / f'{wafer}_{name}_trend_full.png'
    canvas.save(full)
    preview = data_preview(canvas)
    preview.save(output / f'{wafer}_{name}_trend_preview.png')
    print(wafer, name, dict(counts), flush=True)
    return preview, dict(counts)


def position_statistics(records, ranges, min_count):
    result = []
    for slot, die in sorted(SLOTS.items(), key=lambda item: item[1]):
        row, col = POSITIONS[die]
        entry = dict(slot=slot, die_number=die, wafer_grid_row=row, wafer_grid_col=col)
        for name, (low, high) in ranges.items():
            values = []
            for wafer_number in range(1, 8):
                record = records.get(f'0RUZS{wafer_number:02d}{slot}')
                value = record.get(name) if record else None
                if value is not None and low <= value <= high:
                    values.append(value)
            entry[f'{name}_n'] = len(values)
            entry[f'{name}_mean'] = float(np.mean(values)) if values else None
            entry[f'{name}_std'] = (
                float(np.std(values, ddof=1)) if len(values) >= 2 else None
            )
            entry[f'{name}_sufficient'] = len(values) >= min_count
        result.append(entry)
    return result


def render_position_stat(name, statistic, rows, value_range, min_count, output):
    low, high = value_range
    canvas = Image.new('RGB', CANVAS_SIZE, 'white')
    draw = ImageDraw.Draw(canvas)
    label = 'mean' if statistic == 'mean' else 'sample standard deviation'
    title = f'ALTAI | {PARAMETERS[name]["title"]} position-wise {label}'
    draw_wafer_frame(
        draw, title,
        f'Computed across wafers 01-07 after applying the {TREND_RANGES[name][0]:g}-{TREND_RANGES[name][1]:g} mA trend window; minimum n={min_count}',
    )
    counts = Counter()
    for entry in rows:
        row, col = entry['wafer_grid_row'], entry['wafer_grid_col']
        n = entry[f'{name}_n']
        value = entry[f'{name}_{statistic}']
        if n < min_count or value is None:
            draw.rectangle(tile_rect(row, col), fill=INSUFFICIENT)
            counts['INSUFFICIENT_N'] += 1
            continue
        draw.rectangle(tile_rect(row, col), fill=yellow_color(value, low, high))
        counts['AVAILABLE'] += 1
    draw_legend(
        draw, canvas, low, high, 'mA', counts,
        f'Gray positions have fewer than {min_count} included wafers. Values and n are in position_statistics.csv.',
        gray_label=f'fewer than {min_count} included wafers',
    )
    full = output / f'position_{statistic}_{name}_full.png'
    canvas.save(full)
    preview = data_preview(canvas)
    preview.save(output / f'position_{statistic}_{name}_preview.png')
    return preview, dict(counts)


def normalized_radius(row, col):
    x = col + 0.5
    y = row + 0.5
    raw = math.hypot(x - 5.5, y - 3.0)
    maximum = max(
        math.hypot(c + 0.5 - 5.5, r + 0.5 - 3.0)
        for r, c in POSITIONS.values()
    )
    return raw / maximum


def radial_analysis(name, records, value_range, min_position_count):
    low, high = value_range
    points = []
    for record in records.values():
        value = record.get(name)
        if value is None or not low <= value <= high:
            continue
        radius = normalized_radius(record['wafer_grid_row'], record['wafer_grid_col'])
        points.append((record['wafer'], radius, value, record['chip_id']))
    radius = np.asarray([point[1] for point in points], dtype=float)
    values = np.asarray([point[2] for point in points], dtype=float)
    slope, intercept = np.polyfit(radius, values, 1)
    pearson = float(np.corrcoef(radius, values)[0, 1])
    residual_pairs = []
    for wafer in sorted({point[0] for point in points}):
        group = [point for point in points if point[0] == wafer]
        mean = float(np.mean([point[2] for point in group]))
        residual_pairs.extend((point[1], point[2] - mean) for point in group)
    residuals = np.asarray(residual_pairs, dtype=float)
    centered = float(np.corrcoef(residuals[:, 0], residuals[:, 1])[0, 1])
    by_slot = defaultdict(list)
    for wafer, radius_value, value, chip_id in points:
        by_slot[chip_id[7:]].append((radius_value, value))
    position_points = [
        (values[0][0], float(np.mean([item[1] for item in values])))
        for values in by_slot.values() if len(values) >= min_position_count
    ]
    position_array = np.asarray(position_points, dtype=float)
    position_mean_r = float(np.corrcoef(position_array[:, 0], position_array[:, 1])[0, 1])
    return {
        'parameter': name,
        'n': len(points),
        'window_mA': [low, high],
        'pearson_r': pearson,
        'within_wafer_centered_pearson_r': centered,
        'position_mean_pearson_r': position_mean_r,
        'position_mean_count': len(position_points),
        'slope_mA_per_normalized_radius': float(slope),
        'intercept_mA': float(intercept),
        'radius_basis': 'normalized distance on the schematic 46-position grid',
        'points': points,
    }


def render_radial_scatter(analysis, output):
    name = analysis['parameter']
    low, high = analysis['window_mA']
    width, height = 1800, 1200
    left, right, top, bottom = 190, 90, 150, 170
    canvas = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(canvas)
    plot_right, plot_bottom = width - right, height - bottom
    draw.line((left, top, left, plot_bottom), fill='black', width=4)
    draw.line((left, plot_bottom, plot_right, plot_bottom), fill='black', width=4)
    draw.text((left, 35), f'PowerTest.{name}: current versus schematic radial position', font=font(45), fill='black')
    draw.text(
        (left, 92),
        f'n={analysis["n"]}, individual r={analysis["pearson_r"]:.3f}, within-wafer r={analysis["within_wafer_centered_pearson_r"]:.3f}, '
        f'position-mean r={analysis["position_mean_pearson_r"]:.3f} ({analysis["position_mean_count"]} positions)',
        font=font(31), fill='black',
    )

    def xy(radius, value):
        x = left + radius * (plot_right - left)
        y = plot_bottom - (value - low) / (high - low) * (plot_bottom - top)
        return x, y

    for tick in np.linspace(0, 1, 6):
        x, _ = xy(float(tick), low)
        draw.line((x, plot_bottom, x, plot_bottom + 12), fill='black', width=3)
        draw.text((x, plot_bottom + 25), f'{tick:.1f}', font=font(27), fill='black', anchor='ma')
    for value in np.linspace(low, high, 5):
        _, y = xy(0, float(value))
        draw.line((left - 12, y, left, y), fill='black', width=3)
        draw.text((left - 22, y), f'{value:.1f}', font=font(27), fill='black', anchor='rm')
        draw.line((left, y, plot_right, y), fill=(225, 225, 225), width=1)
    for _, radius, value, _ in analysis['points']:
        x, y = xy(radius, value)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=POINT_COLOR, outline=(90, 70, 0), width=1)
    intercept = analysis['intercept_mA']
    slope = analysis['slope_mA_per_normalized_radius']
    x0, y0 = xy(0, intercept)
    x1, y1 = xy(1, intercept + slope)
    draw.line((x0, y0, x1, y1), fill=FIT_COLOR, width=5)
    draw.text((width // 2, height - 95), 'Normalized radius on schematic die grid', font=font(33), fill='black', anchor='mm')
    label = Image.new('RGBA', (300, 55), (255, 255, 255, 0))
    label_draw = ImageDraw.Draw(label)
    label_draw.text((0, 0), 'Current (mA)', font=font(33), fill='black')
    label = label.rotate(90, expand=True)
    canvas.paste(label, (30, (top + plot_bottom - label.height) // 2), label)
    draw.text(
        (left, height - 50),
        'This radius is based on the schematic die-position map and is not a metrology coordinate.',
        font=font(28), fill=(70, 70, 70),
    )
    canvas.save(output / f'{name}_radial_scatter.png')


def write_position_csv(path, rows):
    columns = [
        'slot', 'die_number', 'wafer_grid_row', 'wafer_grid_col',
        'i_a_n', 'i_a_mean_mA', 'i_a_std_mA',
        'i_d_n', 'i_d_mean_mA', 'i_d_std_mA',
    ]
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                'slot': row['slot'], 'die_number': row['die_number'],
                'wafer_grid_row': row['wafer_grid_row'],
                'wafer_grid_col': row['wafer_grid_col'],
                'i_a_n': row['i_a_n'], 'i_a_mean_mA': row['i_a_mean'],
                'i_a_std_mA': row['i_a_std'],
                'i_d_n': row['i_d_n'], 'i_d_mean_mA': row['i_d_mean'],
                'i_d_std_mA': row['i_d_std'],
            })


def self_test():
    assert 0 <= normalized_radius(*POSITIONS[0]) <= 1
    assert math.isclose(max(normalized_radius(*p) for p in POSITIONS.values()), 1.0)
    assert yellow_color(11.5, 11.5, 14.2) != BLACK
    assert yellow_color(14.2, 11.5, 14.2) != BLACK
    print('Self-test: trend colors, mapping and normalized radius OK')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project-root', type=Path, default=PROJECT)
    parser.add_argument('--output-root', type=Path,
                        help='Default: PROJECT/Results/WaferPowerTrendMaps')
    parser.add_argument('--ia-min', type=float, default=TREND_RANGES['i_a'][0])
    parser.add_argument('--ia-max', type=float, default=TREND_RANGES['i_a'][1])
    parser.add_argument('--id-min', type=float, default=TREND_RANGES['i_d'][0])
    parser.add_argument('--id-max', type=float, default=TREND_RANGES['i_d'][1])
    parser.add_argument('--min-position-count', type=int, default=3)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return
    if args.min_position_count < 2 or args.min_position_count > 7:
        parser.error('--min-position-count must be between 2 and 7')
    ranges = {'i_a': (args.ia_min, args.ia_max), 'i_d': (args.id_min, args.id_max)}
    for name, (low, high) in ranges.items():
        if not math.isfinite(low) or not math.isfinite(high) or low >= high:
            parser.error(f'Require finite {name} minimum < maximum')

    root, latest, run_count, records = collect_records(args.project_root)
    output = (
        args.output_root or args.project_root / 'Results' / 'WaferPowerTrendMaps'
    ) / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    print(f'Discovered {run_count} runs; {len(latest)} unique corrected chips', flush=True)

    wafer_summaries = []
    wafer_previews = defaultdict(list)
    for wafer_number in range(1, 8):
        wafer = f'0RUZS{wafer_number:02d}'
        for name in ('i_a', 'i_d'):
            preview, counts = render_wafer(wafer, name, records, ranges[name], output)
            wafer_previews[name].append(preview)
            wafer_summaries.append({'wafer': wafer, 'parameter': name, 'counts': counts})
    for name, images in wafer_previews.items():
        overview = Image.new('RGB', (3 * 1400, 3 * 1600), 'white')
        for index, preview in enumerate(images):
            overview.paste(preview, ((index % 3) * 1400, (index // 3) * 1600))
        overview.save(output / f'all_wafers_{name}_trend_overview.png')

    positions = position_statistics(records, ranges, args.min_position_count)
    position_previews = []
    position_summaries = []
    for name in ('i_a', 'i_d'):
        for statistic, value_range in (
            ('mean', ranges[name]), ('std', STD_RANGES[name]),
        ):
            preview, counts = render_position_stat(
                name, statistic, positions, value_range,
                args.min_position_count, output,
            )
            position_previews.append(preview)
            position_summaries.append({'parameter': name, 'statistic': statistic, 'counts': counts})
    overview = Image.new('RGB', (2 * 1400, 2 * 1600), 'white')
    for index, preview in enumerate(position_previews):
        overview.paste(preview, ((index % 2) * 1400, (index // 2) * 1600))
    overview.save(output / 'position_statistics_overview.png')

    radial = {}
    for name in ('i_a', 'i_d'):
        analysis = radial_analysis(name, records, ranges[name], args.min_position_count)
        render_radial_scatter(analysis, output)
        radial[name] = {key: value for key, value in analysis.items() if key != 'points'}

    render_id_reference(output)
    write_position_csv(output / 'position_statistics.csv', positions)
    manifest = {
        'batch': BATCH,
        'input_root': str(root),
        'run_count': run_count,
        'unique_corrected_chip_count': len(latest),
        'selection': 'latest run per corrected chip ID; no fallback to older successful runs',
        'trend_windows_mA': {name: list(value) for name, value in ranges.items()},
        'trend_filter': 'Only finite values inside the stated window contribute to yellow maps, position statistics and radial correlations',
        'outside_window_rgb': list(EXCLUDED),
        'missing_unusable_rgb': list(BLACK),
        'minimum_wafers_for_position_maps': args.min_position_count,
        'position_std_ranges_mA': {name: list(value) for name, value in STD_RANGES.items()},
        'radius_caveat': 'normalized schematic grid distance, not physical metrology coordinates',
        'wafer_summaries': wafer_summaries,
        'position_summaries': position_summaries,
        'radial_analysis': radial,
        'position_statistics_file': 'position_statistics.csv',
        'chip_id_reference': 'chip_id_reference.png',
    }
    (output / 'trend_analysis.json').write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + '\n',
    )
    print('Radial analysis:', json.dumps(radial, indent=2), flush=True)
    print(f'OUTPUT: {output}', flush=True)


if __name__ == '__main__':
    main()
