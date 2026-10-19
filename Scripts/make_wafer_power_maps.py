#!/usr/bin/env python3
"""Generate March ALTAI wafer maps for PowerTest.i_a and PowerTest.i_d.

Run: python3 make_wafer_power_maps.py
Dependencies: numpy, Pillow. Input data are read only.
Outputs: Results/WaferPowerMaps/<unique timestamp>/ (never overwritten).

The script reuses the March chip-selection and die-position rules from
make_wafer_threshold_maps.py: latest run per corrected chip ID, seven wafers,
and 46 recorded die positions per wafer. Each die is filled with the scalar
PowerTest value from analyse_output.json.

Default continuous ranges:
  i_a: 10 to 16 mA
  i_d: 40 to 66 mA

Values inside the continuous range use 256 pale-to-deep yellow levels. Values
below it are purple, values above it are red, and missing/unusable data are
black. A red inner border marks a parameter-level NK value according to the
current GOLD/SILVER/BRONZE limits. These parameter grades are not final chip
grades. All original values and statuses are retained in power_values.csv and
manifest.json.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
    COLOR_LUT,
    POSITIONS,
    PROJECT,
    SLOTS,
    TILE_ORIGIN,
    TILE_SIZE,
    data_preview,
    discover,
    font,
    render_id_reference,
    threshold_rgb,
    tile_origin,
)

PARAMETERS = {
    'i_a': {
        'json_key': 'i_a',
        'title': 'PowerTest.i_a (analog current)',
        'default_min': 10.0,
        'default_max': 16.0,
        'gold': (10.42, 15.54),
        'silver': (10.42, 15.54),
        'bronze': (10.42, 15.54),
    },
    'i_d': {
        'json_key': 'i_d',
        'title': 'PowerTest.i_d (digital current)',
        'default_min': 40.0,
        'default_max': 66.0,
        'gold': (40.0, 45.62),
        'silver': (35.6, 46.3),
        'bronze': (30.6, 65.6),
    },
}

LOW_COLOR = (112, 48, 160)
HIGH_COLOR = (220, 35, 35)
NK_BORDER = (255, 0, 0)
BORDER_WIDTH = 18


def parameter_grade(value, spec):
    """Return the best parameter grade, independently of the final chip grade."""
    for grade in ('gold', 'silver', 'bronze'):
        low, high = spec[grade]
        if low <= value <= high:
            return grade.upper()
    return 'NK'


def load_power_values(record):
    """Load both current values once and preserve why a value is unavailable."""
    run = Path(record['run_path'])
    analysis = run / 'analyse_output.json'
    if not analysis.is_file():
        record['power_status'] = (
            'CONTACT_FAIL' if (run / 'CONTACT_FAIL').exists()
            else 'MISSING_ANALYSE_OUTPUT'
        )
        return {}
    try:
        payload = json.loads(analysis.read_text())
    except (OSError, ValueError) as exc:
        record['power_status'] = 'INVALID_ANALYSE_OUTPUT'
        record['power_error'] = str(exc)
        return {}

    power = payload.get('PowerTest')
    if not isinstance(power, dict):
        record['power_status'] = 'MISSING_POWERTEST'
        return {}

    values = {}
    invalid = []
    for name, spec in PARAMETERS.items():
        raw = power.get(spec['json_key'])
        try:
            value = float(raw)
        except (TypeError, ValueError):
            invalid.append(name)
            continue
        if not math.isfinite(value):
            invalid.append(name)
            continue
        values[name] = value
    record['power_status'] = 'AVAILABLE' if values else 'INVALID_POWER_VALUE'
    if invalid:
        record['invalid_or_missing_parameters'] = invalid
    return values


def scalar_color(value, low, high):
    if value < low:
        return LOW_COLOR, 'BELOW_DISPLAY_RANGE'
    if value > high:
        return HIGH_COLOR, 'ABOVE_DISPLAY_RANGE'
    fraction = (value - low) / (high - low)
    return tuple(int(x) for x in threshold_rgb(np.array(fraction))), 'IN_DISPLAY_RANGE'


def draw_common_header(draw, wafer, name, spec, low, high):
    draw.text(
        (180, 65),
        f'ALTAI {wafer} | {spec["title"]} wafer map (46 recorded dies)',
        font=font(67), fill='black',
    )
    draw.text(
        (180, 158),
        'PDF tray coordinates: A1 upper-left; A/B/C top-to-bottom; 1-8 left-to-right',
        font=font(36), fill='black',
    )
    draw.text(
        (180, 212),
        'ATE loading is rotated 180 deg; logical tray IDs are retained',
        font=font(34), fill='black',
    )
    draw.text(
        (180, 260),
        f'{BATCH} | latest run per corrected chip ID | continuous range: {low:g}-{high:g} mA',
        font=font(31), fill='black',
    )


def render_parameter(wafer, name, spec, records, low, high, output):
    canvas = Image.new('RGB', CANVAS_SIZE, 'white')
    draw = ImageDraw.Draw(canvas)
    draw_common_header(draw, wafer, name, spec, low, high)
    draw.ellipse((55, 300, 6545, 6840), outline=(160, 160, 160), width=5)
    draw.polygon([(3260, 6838), (3340, 6838), (3300, 6800)], fill='black')

    status_counts = Counter()
    grade_counts = Counter()
    for slot, die in sorted(SLOTS.items(), key=lambda item: item[1]):
        chip = f'{wafer}{slot}'
        record = records.get(chip)
        row, col = POSITIONS[die]
        x, y = tile_origin(row, col)
        if record is None:
            draw.rectangle((x, y, x + TILE_SIZE[0] - 1, y + TILE_SIZE[1] - 1), fill=BLACK)
            status_counts['MISSING_CHIP'] += 1
            continue

        value = record.get(name)
        if value is None:
            draw.rectangle((x, y, x + TILE_SIZE[0] - 1, y + TILE_SIZE[1] - 1), fill=BLACK)
            status_counts[record['power_status']] += 1
            continue

        color, display_status = scalar_color(value, low, high)
        grade = record[f'{name}_grade']
        draw.rectangle((x, y, x + TILE_SIZE[0] - 1, y + TILE_SIZE[1] - 1), fill=color)
        if grade == 'NK':
            draw.rectangle(
                (x + 1, y + 1, x + TILE_SIZE[0] - 2, y + TILE_SIZE[1] - 2),
                outline=NK_BORDER, width=BORDER_WIDTH,
            )
        status_counts[display_status] += 1
        grade_counts[grade] += 1

    draw.text(
        (180, 6885),
        ' | '.join(f'{key}: {value}' for key, value in status_counts.items()),
        font=font(31), fill='black',
    )
    bar = threshold_rgb(np.tile(np.linspace(0, 1, 1100), (42, 1)))
    canvas.paste(Image.fromarray(bar), (180, 6955))
    draw.text(
        (180, 7005),
        f'{low:g} mA (light)                         {high:g} mA (dark)',
        font=font(30), fill='black',
    )
    draw.rectangle((1580, 6955, 1635, 6997), fill=LOW_COLOR)
    draw.text((1660, 6955), f'< {low:g} mA', font=font(30), fill='black')
    draw.rectangle((2050, 6955, 2105, 6997), fill=HIGH_COLOR)
    draw.text((2130, 6955), f'> {high:g} mA', font=font(30), fill='black')
    draw.rectangle((2515, 6955, 2570, 6997), fill=BLACK)
    draw.text((2595, 6955), 'missing / contact fail / invalid', font=font(30), fill='black')
    draw.rectangle((3850, 6955, 3905, 6997), fill=(255, 245, 120), outline=NK_BORDER, width=8)
    draw.text((3930, 6955), 'red border: parameter NK', font=font(30), fill='black')
    limits = ' | '.join(
        f'{grade.title()} {spec[grade][0]:g}-{spec[grade][1]:g}'
        for grade in ('gold', 'silver', 'bronze')
    )
    draw.text((180, 7070), f'Parameter limits (mA): {limits}', font=font(31), fill='black')
    draw.text(
        (180, 7125),
        '256 yellow levels; values outside the continuous range are not clipped into yellow. Parameter grade is not the final chip grade.',
        font=font(28), fill='black',
    )
    draw.text(
        (180, 7180),
        'Chip IDs: see chip_id_reference.png. Layout is schematic; 46 recorded positions are shown.',
        font=font(30), fill='black',
    )

    full = output / f'{wafer}_{name}_full.png'
    canvas.save(full)
    preview = data_preview(canvas)
    preview.save(output / f'{wafer}_{name}_preview.png')
    print(wafer, name, dict(status_counts), dict(grade_counts), flush=True)
    return preview, dict(status_counts), dict(grade_counts)


def write_csv(path, rows):
    columns = [
        'chip_id', 'raw_chip_id', 'outer', 'run_time', 'run_path',
        'die_number', 'wafer_grid_row', 'wafer_grid_col', 'power_status',
        'i_a_mA', 'i_a_grade', 'i_d_mA', 'i_d_grade',
    ]
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in rows:
            writer.writerow({
                'chip_id': record['chip_id'],
                'raw_chip_id': record.get('raw_chip_id', ''),
                'outer': record.get('outer', ''),
                'run_time': record.get('run_time', ''),
                'run_path': record.get('run_path', ''),
                'die_number': record['die_number'],
                'wafer_grid_row': record['wafer_grid_row_col'][0],
                'wafer_grid_col': record['wafer_grid_row_col'][1],
                'power_status': record['power_status'],
                'i_a_mA': record.get('i_a', ''),
                'i_a_grade': record.get('i_a_grade', ''),
                'i_d_mA': record.get('i_d', ''),
                'i_d_grade': record.get('i_d_grade', ''),
            })


def self_test():
    assert parameter_grade(12.0, PARAMETERS['i_a']) == 'GOLD'
    assert parameter_grade(10.0, PARAMETERS['i_a']) == 'NK'
    assert parameter_grade(43.0, PARAMETERS['i_d']) == 'GOLD'
    assert parameter_grade(46.0, PARAMETERS['i_d']) == 'SILVER'
    assert parameter_grade(60.0, PARAMETERS['i_d']) == 'BRONZE'
    assert parameter_grade(70.0, PARAMETERS['i_d']) == 'NK'
    assert scalar_color(9, 10, 16) == (LOW_COLOR, 'BELOW_DISPLAY_RANGE')
    assert scalar_color(17, 10, 16) == (HIGH_COLOR, 'ABOVE_DISPLAY_RANGE')
    midpoint, status = scalar_color(13, 10, 16)
    assert status == 'IN_DISPLAY_RANGE' and midpoint not in (BLACK, LOW_COLOR, HIGH_COLOR)
    assert len(COLOR_LUT) == 256
    print('Self-test: parameter grades, display ranges and 256-level colors OK')


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--project-root', type=Path, default=PROJECT)
    parser.add_argument('--output-root', type=Path,
                        help='Default: PROJECT/Results/WaferPowerMaps')
    parser.add_argument('--wafer', action='append',
                        choices=[f'0RUZS{i:02d}' for i in range(1, 8)],
                        help='Repeat to select wafers; default all seven')
    parser.add_argument('--ia-min', type=float, default=10.0)
    parser.add_argument('--ia-max', type=float, default=16.0)
    parser.add_argument('--id-min', type=float, default=40.0)
    parser.add_argument('--id-max', type=float, default=66.0)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    self_test()
    if args.self_test:
        return
    ranges = {'i_a': (args.ia_min, args.ia_max), 'i_d': (args.id_min, args.id_max)}
    for name, (low, high) in ranges.items():
        if not math.isfinite(low) or not math.isfinite(high) or low >= high:
            parser.error(f'Require finite {name} minimum < maximum')

    root = args.project_root.resolve() / 'testdata' / BATCH
    latest, n_runs = discover(root)
    print(f'Discovered {n_runs} runs; {len(latest)} unique corrected chips', flush=True)
    output = (
        args.output_root or args.project_root / 'Results' / 'WaferPowerMaps'
    ) / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)

    records = {}
    for chip, source in latest.items():
        record = dict(source)
        values = load_power_values(record)
        for name, value in values.items():
            record[name] = value
            record[f'{name}_grade'] = parameter_grade(value, PARAMETERS[name])
        slot = chip[7:]
        die = SLOTS[slot]
        record['die_number'] = die
        record['wafer_grid_row_col'] = list(POSITIONS[die])
        records[chip] = record

    selected_wafers = sorted(set(args.wafer or [f'0RUZS{i:02d}' for i in range(1, 8)]))
    previews = {name: [] for name in PARAMETERS}
    map_summaries = []
    for wafer in selected_wafers:
        for name, spec in PARAMETERS.items():
            low, high = ranges[name]
            preview, status_counts, grade_counts = render_parameter(
                wafer, name, spec, records, low, high, output,
            )
            previews[name].append(preview)
            map_summaries.append({
                'wafer': wafer,
                'parameter': name,
                'display_status_counts': status_counts,
                'parameter_grade_counts': grade_counts,
            })

    for name, images in previews.items():
        overview = Image.new('RGB', (3 * 1400, ((len(images) + 2) // 3) * 1600), 'white')
        for index, preview in enumerate(images):
            overview.paste(preview, ((index % 3) * 1400, (index // 3) * 1600))
        overview.save(output / f'all_wafers_{name}_overview.png')

    render_id_reference(output)
    selected_records = [
        records[f'{wafer}{slot}']
        for wafer in selected_wafers
        for slot, _ in sorted(SLOTS.items(), key=lambda item: item[1])
        if f'{wafer}{slot}' in records
    ]
    write_csv(output / 'power_values.csv', selected_records)

    manifest = {
        'batch': BATCH,
        'input_root': str(root),
        'run_count': n_runs,
        'unique_corrected_chip_count': len(latest),
        'selected_wafers': selected_wafers,
        'mapping_source': 'User-supplied Die Picking Rule.pdf',
        'mapping_status': '46 recorded March positions per wafer',
        'selection': 'latest run per corrected chip ID; no fallback to older successful runs',
        'units': 'mA',
        'display_ranges': {name: list(value) for name, value in ranges.items()},
        'display_policy': {
            'within_range': '256 pale-to-deep yellow levels',
            'below_range_rgb': list(LOW_COLOR),
            'above_range_rgb': list(HIGH_COLOR),
            'missing_unusable_rgb': list(BLACK),
            'parameter_nk_inner_border_rgb': list(NK_BORDER),
        },
        'parameter_limits': {
            name: {grade: list(spec[grade]) for grade in ('gold', 'silver', 'bronze')}
            for name, spec in PARAMETERS.items()
        },
        'grade_scope': 'parameter-level only; not the final chip grade',
        'color_mapping': 'index=round(255*clip((value-min)/(max-min),0,1)); yellow LUT inherited from make_wafer_threshold_maps.py',
        'color_levels': 256,
        'chip_id_reference': 'chip_id_reference.png',
        'value_table': 'power_values.csv',
        'map_summaries': map_summaries,
        'records': selected_records,
    }
    (output / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + '\n',
    )
    print(f'OUTPUT: {output}', flush=True)


if __name__ == '__main__':
    main()
