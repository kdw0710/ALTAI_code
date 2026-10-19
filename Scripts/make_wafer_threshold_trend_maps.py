#!/usr/bin/env python3
"""Analyze March ALTAI wafer-level trends in per-chip threshold maps.

Run: python3 make_wafer_threshold_trend_maps.py
Dependencies: numpy, Pillow. Inputs are read only.
Outputs: Results/WaferThresholdTrendMaps/<unique timestamp>/ (never overwritten).

For each latest March chip run, the representative value is the median of the
positive finite pixels in Threshold_Scan_Queue/thrmap.npy. This is a robust
map-derived statistic and is not the final chip grade. The output separates the
all-usable correlation from a normal-detail-window correlation so that extreme
low/high chips cannot silently create an apparent radial trend.
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
    load_map,
    render_id_reference,
    threshold_rgb,
    tile_origin,
)


DEFAULT_DETAIL_RANGE = (6.0, 11.2)
DEFAULT_STD_RANGE = (0.0, 3.5)
LOW_COLOR = (112, 48, 160)
HIGH_COLOR = (220, 35, 35)
INSUFFICIENT = (155, 155, 155)
POINT_COLOR = (226, 178, 0)
FIT_COLOR = (30, 90, 190)


def tile_rect(row, col):
    x, y = tile_origin(row, col)
    return x, y, x + TILE_SIZE[0] - 1, y + TILE_SIZE[1] - 1


def normalized_radius(row, col):
    raw = math.hypot(col + 0.5 - 5.5, row + 0.5 - 3.0)
    maximum = max(
        math.hypot(c + 0.5 - 5.5, r + 0.5 - 3.0)
        for r, c in POSITIONS.values()
    )
    return raw / maximum


def scalar_color(value, low, high):
    if value < low:
        return LOW_COLOR, 'BELOW_DETAIL_RANGE'
    if value > high:
        return HIGH_COLOR, 'ABOVE_DETAIL_RANGE'
    fraction = np.clip((value - low) / (high - low), 0, 1)
    return tuple(int(x) for x in threshold_rgb(np.array(fraction))), 'IN_DETAIL_RANGE'


def collect(project_root):
    root = project_root.resolve() / 'testdata' / BATCH
    latest, run_count = discover(root)
    records = {}
    for chip, source in latest.items():
        record = dict(source)
        array = load_map(record)
        record['threshold_trend_status'] = record['map_status']
        if array is not None:
            valid = array[np.isfinite(array) & (array > 0)]
            if valid.size:
                record.update(
                    threshold_trend_status='USABLE',
                    threshold_median_dac=float(np.median(valid)),
                    threshold_mean_dac=float(np.mean(valid)),
                    threshold_std_dac=float(np.std(valid)),
                    threshold_valid_pixel_count=int(valid.size),
                )
            else:
                record['threshold_trend_status'] = 'NO_POSITIVE_FINITE_PIXELS'
        slot = chip[7:]
        die = SLOTS[slot]
        row, col = POSITIONS[die]
        record.update(
            slot=slot,
            die_number=die,
            wafer=chip[:7],
            wafer_grid_row=row,
            wafer_grid_col=col,
            normalized_schematic_radius=normalized_radius(row, col),
        )
        records[chip] = record
    return root, latest, run_count, records


def draw_frame(draw, title, subtitle):
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


def draw_value_legend(draw, canvas, low, high, counts, gray_label=None, extra=''):
    draw.text(
        (180, 6885), ' | '.join(f'{key}: {value}' for key, value in counts.items()),
        font=font(31), fill='black',
    )
    bar = threshold_rgb(np.tile(np.linspace(0, 1, 1100), (42, 1)))
    canvas.paste(Image.fromarray(bar), (180, 6955))
    draw.text(
        (180, 7005), f'{low:g} DAC (light)                         {high:g} DAC (dark)',
        font=font(30), fill='black',
    )
    draw.rectangle((1580, 6955, 1635, 6997), fill=LOW_COLOR)
    draw.text((1660, 6955), f'< {low:g} DAC', font=font(30), fill='black')
    draw.rectangle((2090, 6955, 2145, 6997), fill=HIGH_COLOR)
    draw.text((2170, 6955), f'> {high:g} DAC', font=font(30), fill='black')
    draw.rectangle((2600, 6955, 2655, 6997), fill=BLACK)
    draw.text((2680, 6955), 'missing / contact fail / unusable', font=font(30), fill='black')
    if gray_label:
        draw.rectangle((4130, 6955, 4185, 6997), fill=INSUFFICIENT)
        draw.text((4210, 6955), gray_label, font=font(30), fill='black')
    draw.text(
        (180, 7070),
        'Each die is one chip-level median calculated from positive finite threshold-map pixels.',
        font=font(31), fill='black',
    )
    draw.text((180, 7130), extra, font=font(29), fill='black')
    draw.text(
        (180, 7180), 'Chip IDs: see chip_id_reference.png. No missing chip or pixel is interpolated.',
        font=font(30), fill='black',
    )


def render_wafer(wafer, records, detail_range, output):
    low, high = detail_range
    canvas = Image.new('RGB', CANVAS_SIZE, 'white')
    draw = ImageDraw.Draw(canvas)
    draw_frame(
        draw,
        f'ALTAI {wafer} | chip-median Threshold trend map',
        f'Detail range: {low:g}-{high:g} DAC; purple/red retain usable low/high outliers',
    )
    counts = Counter()
    for slot, die in sorted(SLOTS.items(), key=lambda item: item[1]):
        chip = f'{wafer}{slot}'
        row, col = POSITIONS[die]
        record = records.get(chip)
        if record is None or record['threshold_trend_status'] != 'USABLE':
            draw.rectangle(tile_rect(row, col), fill=BLACK)
            key = 'MISSING_CHIP' if record is None else record['threshold_trend_status']
            counts[key] += 1
            continue
        color, status = scalar_color(record['threshold_median_dac'], low, high)
        draw.rectangle(tile_rect(row, col), fill=color)
        counts[status] += 1
    draw_value_legend(
        draw, canvas, low, high, counts,
        extra='Purple/red values remain part of the all-usable radial analysis but not the detail-window fit.',
    )
    full = output / f'{wafer}_threshold_median_full.png'
    canvas.save(full)
    preview = data_preview(canvas)
    preview.save(output / f'{wafer}_threshold_median_preview.png')
    print(wafer, dict(counts), flush=True)
    return preview, dict(counts)


def position_statistics(records, min_count):
    rows = []
    for slot, die in sorted(SLOTS.items(), key=lambda item: item[1]):
        values = [
            record['threshold_median_dac']
            for record in records.values()
            if record['slot'] == slot and record['threshold_trend_status'] == 'USABLE'
        ]
        row, col = POSITIONS[die]
        rows.append({
            'slot': slot,
            'die_number': die,
            'wafer_grid_row': row,
            'wafer_grid_col': col,
            'normalized_schematic_radius': normalized_radius(row, col),
            'n': len(values),
            'mean_of_chip_medians_dac': float(np.mean(values)) if values else None,
            'median_of_chip_medians_dac': float(np.median(values)) if values else None,
            'sample_std_of_chip_medians_dac': (
                float(np.std(values, ddof=1)) if len(values) >= 2 else None
            ),
            'sufficient': len(values) >= min_count,
        })
    return rows


def render_position_map(statistic, rows, value_range, min_count, output):
    low, high = value_range
    canvas = Image.new('RGB', CANVAS_SIZE, 'white')
    draw = ImageDraw.Draw(canvas)
    label = {
        'mean_of_chip_medians_dac': 'mean of chip medians',
        'sample_std_of_chip_medians_dac': 'sample standard deviation of chip medians',
    }[statistic]
    draw_frame(
        draw,
        f'ALTAI | position-wise Threshold {label}',
        f'Computed across wafers 01-07 using every usable positive-finite chip median; minimum n={min_count}',
    )
    counts = Counter()
    for entry in rows:
        row, col = entry['wafer_grid_row'], entry['wafer_grid_col']
        value = entry[statistic]
        if not entry['sufficient'] or value is None:
            draw.rectangle(tile_rect(row, col), fill=INSUFFICIENT)
            counts['INSUFFICIENT_N'] += 1
            continue
        color, status = scalar_color(value, low, high)
        draw.rectangle(tile_rect(row, col), fill=color)
        counts[status] += 1
    draw_value_legend(
        draw, canvas, low, high, counts,
        gray_label=f'fewer than {min_count} usable wafers',
        extra='Exact values and contributing-wafer counts are recorded in position_statistics.csv.',
    )
    short = 'mean' if statistic.startswith('mean') else 'std'
    canvas.save(output / f'position_threshold_{short}_full.png')
    preview = data_preview(canvas)
    preview.save(output / f'position_threshold_{short}_preview.png')
    return preview, dict(counts)


def correlation(points, min_position_count):
    radius = np.asarray([point['radius'] for point in points], dtype=float)
    values = np.asarray([point['value'] for point in points], dtype=float)
    slope, intercept = np.polyfit(radius, values, 1)
    residual_pairs = []
    for wafer in sorted({point['wafer'] for point in points}):
        group = [point for point in points if point['wafer'] == wafer]
        mean = float(np.mean([point['value'] for point in group]))
        residual_pairs.extend((point['radius'], point['value'] - mean) for point in group)
    residuals = np.asarray(residual_pairs, dtype=float)
    by_slot = defaultdict(list)
    for point in points:
        by_slot[point['slot']].append(point)
    position_points = [
        (group[0]['radius'], float(np.mean([point['value'] for point in group])))
        for group in by_slot.values() if len(group) >= min_position_count
    ]
    position_array = np.asarray(position_points, dtype=float)
    position_r = (
        float(np.corrcoef(position_array[:, 0], position_array[:, 1])[0, 1])
        if len(position_array) >= 2 else None
    )
    return {
        'n': len(points),
        'pearson_r': float(np.corrcoef(radius, values)[0, 1]),
        'within_wafer_centered_pearson_r': float(np.corrcoef(residuals[:, 0], residuals[:, 1])[0, 1]),
        'position_mean_pearson_r': position_r,
        'position_mean_count': len(position_points),
        'slope_dac_per_normalized_radius': float(slope),
        'intercept_dac': float(intercept),
    }


def radial_analyses(records, detail_range, min_position_count):
    all_points = [
        {
            'chip_id': record['chip_id'], 'wafer': record['wafer'],
            'slot': record['slot'], 'radius': record['normalized_schematic_radius'],
            'value': record['threshold_median_dac'],
        }
        for record in records.values() if record['threshold_trend_status'] == 'USABLE'
    ]
    low, high = detail_range
    detail_points = [point for point in all_points if low <= point['value'] <= high]
    return {
        'all_usable': {**correlation(all_points, min_position_count), 'points': all_points},
        'detail_window': {
            **correlation(detail_points, min_position_count),
            'window_dac': [low, high], 'points': detail_points,
        },
    }


def radial_bins(points):
    bins = [(0.0, 0.33, 'center'), (0.33, 0.66, 'middle'), (0.66, 1.000001, 'edge')]
    output = []
    for low, high, label in bins:
        values = [point['value'] for point in points if low <= point['radius'] < high]
        output.append({
            'region': label, 'radius_range': [low, min(high, 1.0)],
            'n': len(values), 'mean_dac': float(np.mean(values)),
            'median_dac': float(np.median(values)),
            'sample_std_dac': float(np.std(values, ddof=1)) if len(values) >= 2 else None,
        })
    return output


def render_scatter(name, analysis, y_range, detail_range, output):
    points = analysis['points']
    ymin, ymax = y_range
    width, height = 1800, 1200
    left, right, top, bottom = 190, 90, 155, 170
    plot_right, plot_bottom = width - right, height - bottom
    canvas = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(canvas)
    label = 'all usable values' if name == 'all_usable' else f'detail window {detail_range[0]:g}-{detail_range[1]:g} DAC'
    draw.text((left, 35), f'Threshold median vs radius: {label}', font=font(43), fill='black')
    draw.text(
        (left, 92),
        f'n={analysis["n"]}, individual r={analysis["pearson_r"]:.3f}, within-wafer r={analysis["within_wafer_centered_pearson_r"]:.3f}, '
        f'position-mean r={analysis["position_mean_pearson_r"]:.3f} ({analysis["position_mean_count"]} positions)',
        font=font(29), fill='black',
    )
    draw.line((left, top, left, plot_bottom), fill='black', width=4)
    draw.line((left, plot_bottom, plot_right, plot_bottom), fill='black', width=4)

    def xy(radius, value):
        x = left + radius * (plot_right - left)
        y = plot_bottom - (value - ymin) / (ymax - ymin) * (plot_bottom - top)
        return x, y

    for tick in np.linspace(0, 1, 6):
        x, _ = xy(float(tick), ymin)
        draw.line((x, plot_bottom, x, plot_bottom + 12), fill='black', width=3)
        draw.text((x, plot_bottom + 25), f'{tick:.1f}', font=font(27), fill='black', anchor='ma')
    for value in np.linspace(ymin, ymax, 6):
        _, y = xy(0, float(value))
        draw.line((left - 12, y, left, y), fill='black', width=3)
        draw.text((left - 22, y), f'{value:.1f}', font=font(27), fill='black', anchor='rm')
        draw.line((left, y, plot_right, y), fill=(225, 225, 225), width=1)
    for point in points:
        x, y = xy(point['radius'], point['value'])
        color, _ = scalar_color(point['value'], *detail_range)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color, outline=(70, 70, 0), width=1)
    intercept = analysis['intercept_dac']
    slope = analysis['slope_dac_per_normalized_radius']
    x0, y0 = xy(0, intercept)
    x1, y1 = xy(1, intercept + slope)
    draw.line((x0, y0, x1, y1), fill=FIT_COLOR, width=5)
    draw.text((width // 2, height - 95), 'Normalized radius on schematic die grid', font=font(33), fill='black', anchor='mm')
    vertical = Image.new('RGBA', (340, 55), (255, 255, 255, 0))
    ImageDraw.Draw(vertical).text((0, 0), 'Chip median (DAC)', font=font(33), fill='black')
    vertical = vertical.rotate(90, expand=True)
    canvas.paste(vertical, (22, (top + plot_bottom - vertical.height) // 2), vertical)
    draw.text(
        (left, height - 50),
        'Radius is based on the schematic 46-position layout, not physical metrology coordinates.',
        font=font(28), fill=(70, 70, 70),
    )
    canvas.save(output / f'threshold_radial_{name}.png')


def box_summary(values):
    values = np.asarray(sorted(values), dtype=float)
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    iqr = q3 - q1
    low_fence = q1 - 1.5 * iqr
    high_fence = q3 + 1.5 * iqr
    inside = values[(values >= low_fence) & (values <= high_fence)]
    outliers = values[(values < low_fence) | (values > high_fence)]
    return {
        'n': int(values.size),
        'q1': float(q1),
        'median': float(median),
        'q3': float(q3),
        'lower_whisker': float(inside.min()),
        'upper_whisker': float(inside.max()),
        'outliers': [float(value) for value in outliers],
    }


def render_boxplot(title, groups, y_range, detail_range, output_path, note):
    width, height = 1800, 1200
    left, right, top, bottom = 180, 80, 175, 205
    plot_right, plot_bottom = width - right, height - bottom
    ymin, ymax = y_range
    canvas = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.text((left, 35), title, font=font(45), fill='black')
    draw.text(
        (left, 95),
        'Box: Q1-Q3 | center line: median | whiskers: most extreme values within 1.5 x IQR | circles: outliers',
        font=font(27), fill='black',
    )
    draw.line((left, top, left, plot_bottom), fill='black', width=4)
    draw.line((left, plot_bottom, plot_right, plot_bottom), fill='black', width=4)

    def y_position(value):
        return plot_bottom - (value - ymin) / (ymax - ymin) * (plot_bottom - top)

    for value in np.linspace(ymin, ymax, 6):
        y = y_position(float(value))
        draw.line((left - 12, y, left, y), fill='black', width=3)
        draw.text((left - 22, y), f'{value:.1f}', font=font(27), fill='black', anchor='rm')
        draw.line((left, y, plot_right, y), fill=(225, 225, 225), width=1)

    summaries = {}
    group_width = (plot_right - left) / len(groups)
    box_width = min(170, group_width * 0.42)
    for index, (label, values) in enumerate(groups):
        if not values:
            continue
        summary = box_summary(values)
        summaries[label] = summary
        x = left + (index + 0.5) * group_width
        q1_y, median_y, q3_y = (
            y_position(summary['q1']), y_position(summary['median']),
            y_position(summary['q3']),
        )
        lower_y = y_position(summary['lower_whisker'])
        upper_y = y_position(summary['upper_whisker'])
        draw.line((x, upper_y, x, q3_y), fill='black', width=4)
        draw.line((x, q1_y, x, lower_y), fill='black', width=4)
        draw.line((x - box_width * 0.28, upper_y, x + box_width * 0.28, upper_y), fill='black', width=4)
        draw.line((x - box_width * 0.28, lower_y, x + box_width * 0.28, lower_y), fill='black', width=4)
        draw.rectangle(
            (x - box_width / 2, q3_y, x + box_width / 2, q1_y),
            fill=(255, 235, 55), outline='black', width=4,
        )
        draw.line((x - box_width / 2, median_y, x + box_width / 2, median_y), fill=(180, 25, 25), width=6)
        for outlier_index, value in enumerate(summary['outliers']):
            jitter = ((outlier_index % 5) - 2) * 7
            y = y_position(value)
            color, _ = scalar_color(value, *detail_range)
            draw.ellipse((x + jitter - 7, y - 7, x + jitter + 7, y + 7), fill=color, outline='black', width=1)
        draw.text((x, plot_bottom + 28), label, font=font(31), fill='black', anchor='ma')
        draw.text((x, plot_bottom + 70), f'n={summary["n"]}', font=font(25), fill=(70, 70, 70), anchor='ma')
    vertical = Image.new('RGBA', (340, 55), (255, 255, 255, 0))
    ImageDraw.Draw(vertical).text((0, 0), 'Chip median (DAC)', font=font(33), fill='black')
    vertical = vertical.rotate(90, expand=True)
    canvas.paste(vertical, (18, (top + plot_bottom - vertical.height) // 2), vertical)
    draw.text((left, height - 60), note, font=font(27), fill=(70, 70, 70))
    canvas.save(output_path)
    return canvas, summaries


def make_boxplots(analyses, detail_range, output):
    all_points = analyses['all_usable']['points']
    detail_points = analyses['detail_window']['points']

    def radial_groups(points):
        definitions = [(0.0, 0.33, 'Center'), (0.33, 0.66, 'Middle'), (0.66, 1.000001, 'Edge')]
        return [
            (label, [point['value'] for point in points if low <= point['radius'] < high])
            for low, high, label in definitions
        ]

    def wafer_groups(points):
        return [
            (f'{number:02d}', [point['value'] for point in points if point['wafer'] == f'0RUZS{number:02d}'])
            for number in range(1, 8)
        ]

    all_values = [point['value'] for point in all_points]
    all_range = (math.floor(min(all_values)), math.ceil(max(all_values)))
    plots = []
    summaries = {}
    specifications = [
        ('radial_all_usable', 'Threshold distribution by radial region: all usable values', radial_groups(all_points), all_range,
         'The apparent radial difference includes low/high threshold outliers.'),
        ('radial_detail_window', f'Threshold distribution by radial region: {detail_range[0]:g}-{detail_range[1]:g} DAC', radial_groups(detail_points), detail_range,
         'Only chip medians inside the detail window are included.'),
        ('wafer_all_usable', 'Threshold distribution by wafer: all usable values', wafer_groups(all_points), all_range,
         'Wafer labels 01-07; every usable chip-median threshold is included.'),
        ('wafer_detail_window', f'Threshold distribution by wafer: {detail_range[0]:g}-{detail_range[1]:g} DAC', wafer_groups(detail_points), detail_range,
         'Wafer labels 01-07; only chip medians inside the detail window are included.'),
    ]
    for name, title, groups, y_range, note in specifications:
        canvas, summary = render_boxplot(
            title, groups, y_range, detail_range,
            output / f'threshold_boxplot_{name}.png', note,
        )
        plots.append(canvas)
        summaries[name] = {
            label: {key: value for key, value in stats.items() if key != 'outliers'} | {'outlier_count': len(stats['outliers'])}
            for label, stats in summary.items()
        }
    overview = Image.new('RGB', (1800, 1200), 'white')
    for index, canvas in enumerate(plots):
        preview = canvas.resize((900, 600), Image.Resampling.LANCZOS)
        overview.paste(preview, ((index % 2) * 900, (index // 2) * 600))
    overview.save(output / 'threshold_boxplots_overview.png')
    return summaries


def write_chip_csv(path, records, detail_range):
    columns = [
        'chip_id', 'raw_chip_id', 'outer', 'run_time', 'run_path', 'slot',
        'die_number', 'wafer_grid_row', 'wafer_grid_col',
        'normalized_schematic_radius', 'threshold_trend_status',
        'threshold_median_dac', 'threshold_mean_dac', 'threshold_std_dac',
        'threshold_valid_pixel_count', 'inside_detail_range',
    ]
    low, high = detail_range
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in sorted(records.values(), key=lambda item: item['chip_id']):
            value = record.get('threshold_median_dac')
            writer.writerow({
                key: (
                    low <= value <= high if key == 'inside_detail_range' and value is not None
                    else record.get(key, '')
                )
                for key in columns
            })


def write_position_csv(path, rows):
    columns = [
        'slot', 'die_number', 'wafer_grid_row', 'wafer_grid_col',
        'normalized_schematic_radius', 'n', 'mean_of_chip_medians_dac',
        'median_of_chip_medians_dac', 'sample_std_of_chip_medians_dac',
    ]
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in columns})


def self_test():
    assert math.isclose(max(normalized_radius(*p) for p in POSITIONS.values()), 1.0)
    assert scalar_color(5, 6, 11.2)[0] == LOW_COLOR
    assert scalar_color(12, 6, 11.2)[0] == HIGH_COLOR
    assert scalar_color(8, 6, 11.2)[1] == 'IN_DETAIL_RANGE'
    summary = box_summary([1, 2, 3, 4, 100])
    assert summary['median'] == 3 and summary['outliers'] == [100.0]
    print('Self-test: scalar colors, mapping and normalized radius OK')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project-root', type=Path, default=PROJECT)
    parser.add_argument('--output-root', type=Path,
                        help='Default: PROJECT/Results/WaferThresholdTrendMaps')
    parser.add_argument('--detail-min', type=float, default=DEFAULT_DETAIL_RANGE[0])
    parser.add_argument('--detail-max', type=float, default=DEFAULT_DETAIL_RANGE[1])
    parser.add_argument('--std-max', type=float, default=DEFAULT_STD_RANGE[1])
    parser.add_argument('--min-position-count', type=int, default=3)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return
    detail_range = (args.detail_min, args.detail_max)
    if not all(math.isfinite(x) for x in (*detail_range, args.std_max)):
        parser.error('All ranges must be finite')
    if detail_range[0] >= detail_range[1] or args.std_max <= 0:
        parser.error('Require detail-min < detail-max and std-max > 0')
    if not 2 <= args.min_position_count <= 7:
        parser.error('--min-position-count must be between 2 and 7')

    root, latest, run_count, records = collect(args.project_root)
    output = (
        args.output_root or args.project_root / 'Results' / 'WaferThresholdTrendMaps'
    ) / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    print(f'Discovered {run_count} runs; {len(latest)} unique corrected chips', flush=True)

    previews = []
    wafer_summaries = []
    for wafer_number in range(1, 8):
        wafer = f'0RUZS{wafer_number:02d}'
        preview, counts = render_wafer(wafer, records, detail_range, output)
        previews.append(preview)
        wafer_summaries.append({'wafer': wafer, 'counts': counts})
    overview = Image.new('RGB', (3 * 1400, 3 * 1600), 'white')
    for index, preview in enumerate(previews):
        overview.paste(preview, ((index % 3) * 1400, (index // 3) * 1600))
    overview.save(output / 'all_wafers_threshold_median_overview.png')

    positions = position_statistics(records, args.min_position_count)
    mean_preview, mean_counts = render_position_map(
        'mean_of_chip_medians_dac', positions, detail_range,
        args.min_position_count, output,
    )
    std_preview, std_counts = render_position_map(
        'sample_std_of_chip_medians_dac', positions, (0.0, args.std_max),
        args.min_position_count, output,
    )
    position_overview = Image.new('RGB', (2 * 1400, 1600), 'white')
    position_overview.paste(mean_preview, (0, 0))
    position_overview.paste(std_preview, (1400, 0))
    position_overview.save(output / 'position_threshold_statistics_overview.png')

    analyses = radial_analyses(records, detail_range, args.min_position_count)
    all_values = [point['value'] for point in analyses['all_usable']['points']]
    all_y_range = (math.floor(min(all_values)), math.ceil(max(all_values)))
    render_scatter('all_usable', analyses['all_usable'], all_y_range, detail_range, output)
    render_scatter('detail_window', analyses['detail_window'], detail_range, detail_range, output)
    bin_summaries = {
        name: radial_bins(analysis['points']) for name, analysis in analyses.items()
    }
    boxplot_summaries = make_boxplots(analyses, detail_range, output)

    render_id_reference(output)
    write_chip_csv(output / 'threshold_chip_statistics.csv', records, detail_range)
    write_position_csv(output / 'position_statistics.csv', positions)
    serializable_analyses = {
        name: {key: value for key, value in analysis.items() if key != 'points'}
        for name, analysis in analyses.items()
    }
    status_counts = Counter(record['threshold_trend_status'] for record in records.values())
    manifest = {
        'batch': BATCH,
        'input_root': str(root),
        'run_count': run_count,
        'unique_corrected_chip_count': len(latest),
        'selection': 'latest run per corrected chip ID; no fallback to older successful runs',
        'representative_value': 'median of positive finite pixels in Threshold_Scan_Queue/thrmap.npy',
        'scope_caveat': 'map-derived chip statistic; not the final chip grade',
        'status_counts': dict(status_counts),
        'detail_range_dac': list(detail_range),
        'position_std_display_range_dac': [0.0, args.std_max],
        'minimum_wafers_for_position_maps': args.min_position_count,
        'radial_analysis': serializable_analyses,
        'radial_bin_summaries': bin_summaries,
        'boxplot_definition': 'Tukey box plot: Q1-Q3 box, median line, whiskers to most extreme values within 1.5 x IQR, remaining values as outliers',
        'boxplot_summaries': boxplot_summaries,
        'radius_caveat': 'normalized schematic grid distance, not physical metrology coordinates',
        'wafer_summaries': wafer_summaries,
        'position_map_counts': {'mean': mean_counts, 'std': std_counts},
        'chip_statistics_file': 'threshold_chip_statistics.csv',
        'position_statistics_file': 'position_statistics.csv',
        'chip_id_reference': 'chip_id_reference.png',
    }
    (output / 'trend_analysis.json').write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + '\n',
    )
    print('Status counts:', dict(status_counts), flush=True)
    print('Radial analysis:', json.dumps(serializable_analyses, indent=2), flush=True)
    print('Radial bins:', json.dumps(bin_summaries, indent=2), flush=True)
    print(f'OUTPUT: {output}', flush=True)


if __name__ == '__main__':
    main()
