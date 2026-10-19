#!/usr/bin/env python3
"""Independent, read-only March ALTAI wafer threshold atlas generator.

Run: python3 make_wafer_threshold_maps.py
Dependencies: numpy, Pillow. Inputs: testdata/testdata_260318/**/thrmap.npy.
Outputs: Results/WaferThresholdMaps/<unique timestamp>/ (never overwritten).

Mapping: user-provided Die Picking Rule.pdf. For the PDF view, tray A/B/C =
top/middle/bottom and 1..8 = left/right; A1 is the upper-left pocket. The tray
is physically rotated 180 degrees when loaded into the ATE, but logical slot
names are retained. T = dies 0..22 and B = dies 23..45. The map covers the 46
recorded March dies per wafer, not the later-confirmed 48 usable ALTAI dies.
Default orientation: np.rot90(array, 1), after optional array-axis flips.
Array input is [row y, column x], (512,1024), as in threshold_dataport_queue.py.
Every source pixel occupies exactly one pixel in each full-resolution PNG.
Overview/preview images are downsampled; layout is schematic, not metrology.
Within-die pixel orientation is display-only and is not used for directional
interpretation in the current wafer-level comparison.
Tiles are edge-to-edge with no labels or borders on the measured pixels.
Chip IDs are shown only in a separate, reusable wafer position reference.
Positive finite thresholds use a pale-to-deep yellow scale. Missing maps,
contact failures, and nonpositive/nonfinite pixels are all displayed black;
these distinct states remain separate in manifest.json.
No smoothing, fit repair, interpolation of missing data, or raw-data writes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parent.parent
BATCH = 'testdata_260318'
TRAYS = {
    'T': [[21,20,15,14,5,6,11,2], [22,19,16,13,4,7,10,1],
          [None,18,17,12,3,8,9,0]],
    'B': [[44,45,38,37,24,25,30,31], [43,42,39,36,23,26,29,32],
          [None,41,40,35,34,27,28,33]],
}
SLOTS = {f'{side}_{"ABC"[r]}{c+1}': die
         for side, rows in TRAYS.items() for r, row in enumerate(rows)
         for c, die in enumerate(row) if die is not None}
POSITIONS = {}
for row, (start, count, offset) in enumerate([(0,3,4),(3,9,1),(12,11,0),
                                            (23,11,0),(34,9,1),(43,3,4)]):
    POSITIONS.update({start+i:(row,offset+i) for i in range(count)})
BLACK = (0,0,0)
COLORS = {status:BLACK for status in
          ('CONTACT_FAIL','MISSING_MAP','MISSING_CHIP','INVALID_MAP')}
ZERO = BLACK
INVALID = BLACK
# 256 explicit levels: fixed HLS hue=yellow, saturation=1, linear lightness.
# Reserve pure black for unusable data; do not map a valid endpoint to black.
LIGHTNESS_RANGE = (0.95, 0.125)
_lightness = np.linspace(*LIGHTNESS_RANGE, 256)
_yellow = np.minimum(1., 2*_lightness)
_blue = np.maximum(0., 2*_lightness-1.)
COLOR_LUT = np.rint(255*np.column_stack((_yellow,_yellow,_blue))).astype(np.uint8)
CANVAS_SIZE = (6600,7370)
TILE_ORIGIN = (484,450)
TILE_SIZE = (512,1024)

def tile_origin(row,col):
    return TILE_ORIGIN[0]+col*TILE_SIZE[0], TILE_ORIGIN[1]+row*TILE_SIZE[1]

def data_preview(canvas):
    # Smooth annotation text, but never blend threshold colors or missing data.
    preview=canvas.copy()
    preview.thumbnail((1400,1600),Image.Resampling.LANCZOS)
    scale=preview.width/canvas.width
    x0,y0=TILE_ORIGIN
    box=(x0,y0,x0+11*TILE_SIZE[0],y0+6*TILE_SIZE[1])
    target=tuple(round(v*scale) for v in box)
    data=canvas.crop(box).resize((target[2]-target[0],target[3]-target[1]),Image.Resampling.NEAREST)
    preview.paste(data,(target[0],target[1]))
    return preview

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def corrected_id(raw, outer):
    # Same narrowly scoped rule as make_cumulative_result_excel.py.
    if outer.isdigit() and 1772722654 <= int(outer) <= 1772732321:
        if raw.startswith('0RUZS07B_'):
            return raw.replace('0RUZS07B_', '0RUZS07T_', 1)
    return raw

def discover(root):
    """March standard layout; latest run, not latest successful map."""
    latest = {}
    n_runs = 0
    for run in sorted(root.glob('*/*/*')):
        if not run.is_dir() or not re.fullmatch(r'\d{8}-\d{6}',run.name):
            continue
        raw, outer = run.parent.name, run.parent.parent.name
        chip = corrected_id(raw, outer)
        if not re.fullmatch(r'0RUZS0[1-7][TB]_[ABC][1-8]',chip):
            raise ValueError(f'Unexpected March chip ID: {chip} ({run})')
        if chip[7:] not in SLOTS:
            raise ValueError(f'No picking-rule slot for {chip}')
        n_runs += 1
        record = dict(chip_id=chip, raw_chip_id=raw, outer=outer,
                      run_time=run.name, run_path=str(run))
        key = (run.name, BATCH, outer)
        if chip not in latest or key > latest[chip][0]:
            latest[chip] = (key,record)
    if not latest:
        raise ValueError(f'No March run folders found in {root}')
    return {k:v[1] for k,v in latest.items()}, n_runs

def orient(a, rotation, flip_x=False, flip_y=False):
    if flip_x:
        a = np.fliplr(a)
    if flip_y:
        a = np.flipud(a)
    return np.rot90(a, rotation//90)

def load_map(record):
    run = Path(record['run_path'])
    analysis = run/'analyse_output.json'
    # Match existing workbook status precedence, retaining all missing states.
    record['run_status'] = 'NO_ANALYSE_OUTPUT'
    if analysis.is_file():
        try:
            json.loads(analysis.read_text())
            record['run_status'] = 'ANALYZED'
        except (ValueError,OSError):
            record['run_status'] = 'INVALID_ANALYSE_OUTPUT'
    elif (run/'CONTACT_FAIL').exists():
        record['run_status'] = 'CONTACT_FAIL'
    path = run/'Threshold_Scan_Queue'/'thrmap.npy'
    record['map_path'] = str(path)
    if record['run_status'] == 'CONTACT_FAIL':
        record['map_status'] = 'CONTACT_FAIL'
        return None
    if not path.is_file():
        record['map_status'] = 'MISSING_MAP'
        return None
    try:
        a = np.load(path, allow_pickle=False)
        if a.shape != (512,1024) or a.dtype.kind not in 'fiu':
            raise ValueError(f'Expected numeric (512,1024), found {a.shape} {a.dtype}')
        record['source_sha256'] = sha256(path)
        record['map_status'] = 'AVAILABLE'
        record['pixels_total'] = int(a.size)
        record['pixels_zero'] = int(np.count_nonzero(a==0))
        record['pixels_negative_or_nonfinite'] = int(np.count_nonzero((a<0)|~np.isfinite(a)))
        positive = a[np.isfinite(a)&(a>0)]
        record['pixels_positive_finite'] = int(positive.size)
        record['positive_median_dac'] = float(np.median(positive)) if positive.size else None
        return a
    except (ValueError,OSError,EOFError) as exc:
        record['map_status'] = 'INVALID_MAP'
        record['error'] = str(exc)
        return None

def threshold_rgb(fraction):
    fraction=np.clip(fraction,0,1)
    # Linear threshold-to-index mapping, rounded to the nearest of 256 levels.
    index=np.rint(fraction*255).astype(np.uint8)
    return COLOR_LUT[index]

def colorize(a, low, high):
    positive = np.isfinite(a)&(a>0)
    safe = np.where(positive,a,low)
    rgb = threshold_rgb((safe-low)/(high-low))
    rgb[a==0] = ZERO
    rgb[(a<0)|~np.isfinite(a)] = INVALID
    return Image.fromarray(rgb)

def font(size):
    try:
        return ImageFont.truetype('DejaVuSans.ttf',size)
    except OSError:
        return ImageFont.load_default(size=size)

def self_test():
    assert len(SLOTS)==46 and set(SLOTS.values())==set(range(46))
    assert len(set(POSITIONS.values()))==46
    assert SLOTS['T_A4']==14 and SLOTS['T_C8']==0 and SLOTS['B_A1']==44
    assert corrected_id('0RUZS07B_A1','1772722654')=='0RUZS07T_A1'
    assert corrected_id('0RUZS07B_A1','1772732322')=='0RUZS07B_A1'
    a=np.arange(512*1024).reshape(512,1024)
    for angle in (90,270):
        b=orient(a,angle)
        assert b.shape==(1024,512)
        assert np.array_equal(np.rot90(b,-angle//90),a)
    image=np.asarray(colorize(np.array([[0.,-1.,np.nan,5.,10.]]),0,10))
    assert tuple(image[0,0])==ZERO and tuple(image[0,1])==INVALID
    assert tuple(image[0,2])==INVALID and tuple(image[0,4])==tuple(COLOR_LUT[-1])
    palette=threshold_rgb(np.linspace(0,1,256))
    assert np.array_equal(palette,COLOR_LUT)
    assert len(np.unique(palette,axis=0))==256
    assert all(tuple(color)!=BLACK for color in palette)
    assert np.all(palette[:,0]==palette[:,1]) and np.all(palette[:,1]>=palette[:,2])
    assert np.all(np.diff(palette.astype(float) @ [0.2126,0.7152,0.0722])<=0)
    assert tile_origin(0,1)[0]-tile_origin(0,0)[0]==512
    assert tile_origin(1,0)[1]-tile_origin(0,0)[1]==1024
    print('Self-test: mapping bijection, scoped ID correction, orientation and colors OK')

def render(wafer, latest, args, output):
    # Native-pixel tiles touch edge-to-edge; no drawing touches their pixels.
    canvas=Image.new('RGB',CANVAS_SIZE,'white')
    draw=ImageDraw.Draw(canvas)
    draw.text((180,65),f'ALTAI {wafer} | pixel-level Threshold map (46 recorded dies)',font=font(70),fill='black')
    draw.text((180,158),'PDF tray coordinates: A1 upper-left; A/B/C top-to-bottom; 1-8 left-to-right',font=font(36),fill='black')
    draw.text((180,212),'ATE loading is rotated 180 deg; logical tray IDs are retained',font=font(34),fill='black')
    draw.text((180,260),f'{BATCH} | latest run per corrected chip ID | within-chip display: {args.rotation} deg CCW; flip x={args.flip_x}, y={args.flip_y}',font=font(30),fill='black')
    draw.ellipse((55,300,6545,6840),outline=(160,160,160),width=5)
    draw.polygon([(3260,6838),(3340,6838),(3300,6800)],fill='black')
    records=[]
    for slot, die in sorted(SLOTS.items(),key=lambda item:item[1]):
        chip=f'{wafer}{slot}'
        rec=dict(latest.get(chip,dict(chip_id=chip,map_status='MISSING_CHIP')))
        rec['die_number']=die
        row,col=POSITIONS[die]
        rec['wafer_grid_row_col']=[row,col]
        x,y=tile_origin(row,col)
        rec['image_tile_xy']=[x,y]
        a=load_map(rec) if chip in latest else None
        if a is not None:
            positive=np.isfinite(a)&(a>0)
            rec['pixels_below_color_min']=int(np.count_nonzero(positive&(a<args.vmin)))
            rec['pixels_above_color_max']=int(np.count_nonzero(positive&(a>args.vmax)))
            tile=colorize(orient(a,args.rotation,args.flip_x,args.flip_y),args.vmin,args.vmax)
            canvas.paste(tile,(x,y))
        else:
            draw.rectangle((x,y,x+511,y+1023),fill=BLACK)
        records.append(rec)
    counts=Counter(r['map_status'] for r in records)
    draw.text((180,6910),' | '.join(f'{k}: {v}' for k,v in counts.items()),font=font(34),fill='black')
    bar=threshold_rgb(np.tile(np.linspace(0,1,1100),(42,1)))
    canvas.paste(Image.fromarray(bar),(180,6980))
    draw.text((180,7030),f'{args.vmin:g} DAC (light)                         {args.vmax:g} DAC (dark)',font=font(30),fill='black')
    draw.rectangle((1590,6980,1645,7022),fill=BLACK)
    draw.text((1670,6980),'No usable threshold: missing / contact fail / zero / negative / nonfinite',font=font(31),fill='black')
    draw.text((180,7105),'256 yellow lightness levels; out-of-range values saturate. Chip IDs: see chip_id_reference.png.',font=font(31),fill='black')
    draw.text((180,7160),'46 recorded positions; not a complete 48-usable-die layout. Within-chip direction is not interpreted.',font=font(31),fill='black')
    full=output/f'{wafer}_threshold_full.png'
    canvas.save(full)
    preview=data_preview(canvas)
    preview.save(output/f'{wafer}_threshold_preview.png')
    print(wafer,dict(counts),flush=True)
    return records,preview

def render_id_reference(output):
    """One common location key, intentionally separate from all data maps."""
    canvas=Image.new('RGB',CANVAS_SIZE,'white')
    draw=ImageDraw.Draw(canvas)
    draw.text((180,65),'ALTAI | chip ID position reference',font=font(74),fill='black')
    draw.text((180,162),'Common to March wafers: nn = 01, 02, 03, 04, 05, 06, 07',font=font(43),fill='black')
    draw.text((180,230),'PDF view: A1 upper-left; A/B/C top-to-bottom; 1-8 left-to-right',font=font(35),fill='black')
    draw.ellipse((55,300,6545,6840),outline=(160,160,160),width=5)
    draw.polygon([(3260,6838),(3340,6838),(3300,6800)],fill='black')
    for slot,die in SLOTS.items():
        row,col=POSITIONS[die]
        x,y=tile_origin(row,col)
        draw.rectangle((x,y,x+511,y+1023),fill=(229,240,255),outline=(72,104,143),width=5)
        cx,cy=x+256,y+512
        draw.text((cx,cy-155),f'Die {die:02d}',font=font(68),fill=(72,104,143),anchor='mm')
        draw.text((cx,cy), '0RUZSnn',font=font(76),fill=(8,48,107),anchor='mm')
        draw.text((cx,cy+125),slot,font=font(100),fill=(8,48,107),anchor='mm')
    draw.text((180,6950),'Example: 0RUZSnn + T_A4 = 0RUZS01T_A4 for wafer 01 (Die 14).',font=font(43),fill='black')
    draw.text((180,7030),'T: die 0-22; B: die 23-45. Blank tray position C1 is not a recorded die.',font=font(36),fill='black')
    draw.text((180,7110),'Source: user-supplied Die Picking Rule.pdf. ATE tray loading is physically rotated 180 deg.',font=font(32),fill='black')
    canvas.save(output/'chip_id_reference.png')
    canvas.thumbnail((1400,1600),Image.Resampling.LANCZOS)
    canvas.save(output/'chip_id_reference_preview.png')

def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project-root',type=Path,default=PROJECT)
    parser.add_argument('--output-root',type=Path,help='Default: PROJECT/Results/WaferThresholdMaps')
    parser.add_argument('--wafer',action='append',choices=[f'0RUZS{i:02d}' for i in range(1,8)],help='Repeat to select wafers; default all seven')
    parser.add_argument('--vmin',type=float,default=0.)
    parser.add_argument('--vmax',type=float,default=15.)
    parser.add_argument('--rotation',type=int,choices=[90,270],default=90)
    parser.add_argument('--flip-x',action='store_true',help='Flip source columns before rotation')
    parser.add_argument('--flip-y',action='store_true',help='Flip source rows before rotation')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    self_test()
    if args.self_test:
        return
    if not np.isfinite([args.vmin,args.vmax]).all() or args.vmin>=args.vmax:
        parser.error('Require finite vmin < vmax')
    root=args.project_root.resolve()/'testdata'/BATCH
    latest,n_runs=discover(root)
    print(f'Discovered {n_runs} runs; {len(latest)} unique corrected chips',flush=True)
    output=(args.output_root or args.project_root/'Results'/'WaferThresholdMaps')/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True,exist_ok=False)
    records=[]
    previews=[]
    for wafer in sorted(set(args.wafer or [f'0RUZS{i:02d}' for i in range(1,8)])):
        rows,preview=render(wafer,latest,args,output)
        records.extend(rows)
        previews.append(preview)
    overview=Image.new('RGB',(3*1400,((len(previews)+2)//3)*1600),'white')
    for i,p in enumerate(previews):
        overview.paste(p,((i%3)*1400,(i//3)*1600))
    overview.save(output/'all_wafers_overview.png')
    render_id_reference(output)
    manifest=dict(batch=BATCH,input_root=str(root),run_count=n_runs,
        unique_corrected_chip_count=len(latest),mapping_source='User-supplied Die Picking Rule.pdf',
        mapping_status='PDF tray axes confirmed; 46 recorded positions shown, not a complete 48-usable-die ALTAI layout',
        tray_coordinates='PDF view: A/B/C top to bottom; 1..8 left to right; A1 upper-left; T=0..22, B=23..45',
        ate_loading='tray physically rotated 180 degrees relative to the PDF view; logical slot IDs retained',
        orientation=dict(rotation_ccw=args.rotation,flip_source_x=args.flip_x,flip_source_y=args.flip_y,
                         interpretation='display only; within-chip direction is not used in the wafer-level comparison'),
        selection='latest run per corrected chip ID; no fallback to older successful runs',
        color_range_dac=[args.vmin,args.vmax],
        pixel_policy='positive finite values pale-to-deep yellow; all missing states, zero, negative and nonfinite black; original states retained here',
        color_mapping='index=round(255*clip((threshold-vmin)/(vmax-vmin),0,1)); fixed yellow HLS hue, saturation=1; lightness linear in index; not calibrated perceptual luminance',
        color_levels=256,hls_lightness_range=list(LIGHTNESS_RANGE),
        color_lut_rgb=COLOR_LUT.tolist(),
        layout='edge-to-edge native-resolution chip tiles; no IDs or borders on data; schematic, scribe gaps omitted',
        chip_id_reference='chip_id_reference.png',
        preview_resampling='nearest neighbour for data; antialiased annotation text; full PNG preserves every pixel',
        status_counts=dict(Counter(r['map_status'] for r in records)),records=records)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print(f'OUTPUT: {output}',flush=True)

if __name__=='__main__':
    main()
