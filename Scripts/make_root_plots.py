#!/usr/bin/env python3
"""Create ALPIDE-style ROOT distribution plots for cumulative ALTAI data.

The script is designed to live in::

    ALTAI_CHIPTEST_NEW/Scripts/make_root_plots.py

It reads only this project's ``testdata`` directory and writes a new immutable
timestamped run below ``Results/ROOTS``.  Each run contains the cumulative
graphs directly in the run folder and one subfolder per ``testdata_YYMMDD``
batch with the same graph set for that test round.  The chip discovery,
physical Chip ID correction, and classification criteria are imported from the
cumulative Excel script so that both result products use the same
data-selection rules.

PyROOT is imported only when plots are actually produced.  Therefore
``--help`` and ``--dry-run`` can be used before ROOT is installed.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from array import array
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from make_cumulative_result_excel import (
    GRADE_ORDER,
    RESULTS_ROOT,
    TESTDATA_ROOT,
    add_grades,
    build_batch_records,
    collect_records,
    latest_per_chip,
    load_criteria,
    validate_project_layout,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ROOT_RESULTS = RESULTS_ROOT / "ROOTS"

ALPIDE_COLORS = {
    "GOLD": (255, 211, 49),
    "SILVER": (184, 184, 184),
    "BRONZE": (203, 117, 53),
    "NK": (255, 1, 24),
}
LINEAR_AXIS_PADDING_FRACTION = 0.03
LOG_AXIS_PADDING_FACTOR = 1.25
OUTWARD_MAJOR_TICK_LENGTH_NDC = 0.012
DISPLAY_GRADES = ("NK", "BRONZE", "SILVER", "GOLD")
FAKE_HIT_RATE_PARAMETERS = {
    "FakeHitRate.fakerate-10masked",
    "FakeHitRate.fakerate-100masked",
}
FAKE_HIT_RATE_SUMMARY_PARAMETER = "FakeHitRate.combined"
PIXEL_COUNT_PARAMETERS = {
    "AnalogueScanDataPort.num_broken_pixels0",
    "AnalogueScanDataPort.num_dead_pixels0",
    "AnalogueScanDataPort.num_noisy_pixels0",
    "DigitalScan.bad-all",
    "DigitalScan.masked-all",
    "DigitalScan.stuck-all",
    "DigitalScan.unmaskable-all",
    "DigitalScan.unpulsable-all",
}
PILOT_PARAMETERS = (
    "PowerTest.i_d",
    "DigitalScan.stuck-all",
    "FakeHitRate.fakerate-10masked",
)


@dataclass(frozen=True)
class PlotSpec:
    parameter: str
    group: str
    filename: str
    bins: int
    x_min: float
    x_max: float
    log_x: bool = False
    log_y: bool = False
    gaussian: bool = False
    x_title: str = ""
    x_major_step: float | None = None


PLOT_SPECS = (
    PlotSpec(
        "PowerTest.i_d",
        "Powering_Test",
        "PowerTest_i_d",
        80,
        35.0,
        75.0,
        gaussian=True,
        x_title="Digital Current",
        x_major_step=5.0,
    ),
    PlotSpec(
        "PowerTest.i_a",
        "Powering_Test",
        "PowerTest_i_a",
        100,
        0.0,
        25.0,
        gaussian=True,
        x_title="Analog Current",
        x_major_step=5.0,
    ),
    PlotSpec(
        "AnalogueScanDataPort.num_broken_pixels0",
        "Analogue_Scan",
        "Analogue_broken_pixels",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Broken Pixels",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "AnalogueScanDataPort.num_dead_pixels0",
        "Analogue_Scan",
        "Analogue_dead_pixels",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Dead Pixels",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "AnalogueScanDataPort.num_noisy_pixels0",
        "Analogue_Scan",
        "Analogue_noisy_pixels",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Noisy Pixels",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "DigitalScan.bad-all",
        "Digital_Scan",
        "Digital_bad_all",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Digital Scan bad all",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "DigitalScan.masked-all",
        "Digital_Scan",
        "Digital_masked_all",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Digital Scan masked all",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "DigitalScan.stuck-all",
        "Digital_Scan",
        "Digital_stuck_all",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Digital Scan stuck all",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "DigitalScan.unmaskable-all",
        "Digital_Scan",
        "Digital_unmaskable_all",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Digital Scan unmaskable all",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "DigitalScan.unpulsable-all",
        "Digital_Scan",
        "Digital_unpulsable_all",
        100,
        0.0,
        10000.0,
        log_y=True,
        x_title="Digital Scan unpulsable all",
        x_major_step=2000.0,
    ),
    PlotSpec(
        "ThresholdScanDataPortQueue.threshold_npix",
        "Threshold_Scan",
        "Threshold_npix",
        100,
        0.0,
        524288.0,
        log_y=True,
        x_title="Threshold Pixels",
        x_major_step=100000.0,
    ),
    PlotSpec(
        "ThresholdScanDataPortQueue.threshold_mean",
        "Threshold_Scan",
        "Threshold_mean",
        100,
        0.0,
        20.0,
        gaussian=True,
        x_title="Threshold Mean",
        x_major_step=2.5,
    ),
    PlotSpec(
        "ThresholdScanDataPortQueue.threshold_stddev",
        "Threshold_Scan",
        "Threshold_stddev",
        100,
        0.0,
        5.0,
        gaussian=True,
        x_title="Threshold RMS",
        x_major_step=1.0,
    ),
    PlotSpec(
        "ThresholdScanDataPortQueue.stddev_mean_ratio",
        "Threshold_Scan",
        "Threshold_stddev_mean_ratio",
        100,
        0.0,
        0.8,
        gaussian=True,
        x_title="Threshold RMS / Mean",
        x_major_step=0.1,
    ),
    PlotSpec(
        "FakeHitRate.fakerate-10masked",
        "Fake_Hit_Rate",
        "FakeHitRate_10masked",
        70,
        1.0e-10,
        1.0e-3,
        log_x=True,
        log_y=True,
        x_title="Fake Hit Rate 10 pixels masked",
    ),
    PlotSpec(
        "FakeHitRate.fakerate-100masked",
        "Fake_Hit_Rate",
        "FakeHitRate_100masked",
        70,
        1.0e-10,
        1.0e-3,
        log_x=True,
        log_y=True,
        x_title="Fake Hit Rate 100 pixels masked",
    ),
)

SUMMARY_PARAMETERS = (
    ("AnalogueScanDataPort.num_broken_pixels0", "AnalogueScan.num_broken_pixels0"),
    ("AnalogueScanDataPort.num_dead_pixels0", "AnalogueScan.num_dead_pixels0"),
    ("AnalogueScanDataPort.num_noisy_pixels0", "AnalogueScan.num_noisy_pixels0"),
    ("ChipID.chip_id_errors", "ChipID.chip_id_errors"),
    ("DataPort.data_port_errors", "DataPort.data_port_errors"),
    ("DigitalScan.bad-all", "DigitalScan.bad-all"),
    ("DigitalScan.masked-all", "DigitalScan.masked-all"),
    ("DigitalScan.stuck-all", "DigitalScan.stuck-all"),
    ("DigitalScan.unmaskable-all", "DigitalScan.unmaskable-all"),
    ("DigitalScan.unpulsable-all", "DigitalScan.unpulsable-all"),
    ("FIFOTest.fifo_region_errors", "FIFOTest.fifo_region_errors"),
    (FAKE_HIT_RATE_SUMMARY_PARAMETER, "FakeHitRate.fakerate"),
    ("PowerTest.i_d", "PowerTest.i_d"),
    ("PowerTest.i_a", "PowerTest.i_a"),
    ("Registers.errors", "Registers.errors"),
    ("SEU.seus", "SEU.seus"),
    (
        "ThresholdScanDataPortQueue.stddev_mean_ratio",
        "ThresholdScan.stddev_mean_ratio",
    ),
    (
        "ThresholdScanDataPortQueue.threshold_mean",
        "ThresholdScan.threshold_mean",
    ),
    (
        "ThresholdScanDataPortQueue.threshold_npix",
        "ThresholdScan.threshold_npix",
    ),
    (
        "ThresholdScanDataPortQueue.threshold_stddev",
        "ThresholdScan.threshold_stddev",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create ALPIDE-style ALTAI parameter distributions below "
            "Results/ROOTS/YYMMDD_HHMMSS."
        )
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help=(
            "Create only PowerTest.i_d, DigitalScan.stuck-all, and "
            "FakeHitRate.fakerate-10masked distributions, plus the summary."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check data discovery and print plot counts without importing ROOT.",
    )
    parser.add_argument(
        "--with-pdf",
        action="store_true",
        help="Also create a vector PDF copy next to each PNG.",
    )
    parser.add_argument(
        "--annotate-missing",
        action="store_true",
        help=(
            "Show Contact fail and missing-value counts inside each plot. "
            "They are always retained in manifest.json."
        ),
    )
    parser.add_argument(
        "--run-id",
        help=(
            "Optional output folder name in YYMMDD_HHMMSS format. "
            "The current local time is used by default."
        ),
    )
    return parser.parse_args()


def validate_run_id(value: str | None) -> str:
    if value is None:
        return datetime.now().strftime("%y%m%d_%H%M%S")
    try:
        parsed = datetime.strptime(value, "%y%m%d_%H%M%S")
    except ValueError as exc:
        raise ValueError("--run-id must have YYMMDD_HHMMSS format.") from exc
    if parsed.strftime("%y%m%d_%H%M%S") != value:
        raise ValueError("--run-id must have YYMMDD_HHMMSS format.")
    return value


def is_numeric(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def parameter_grade(
    parameter: str,
    value: float,
    cuts: dict[str, dict[str, list[float]]],
) -> str:
    """Return the strictest displayed ALPIDE grade containing the value."""
    for grade in ("GOLD", "SILVER", "BRONZE"):
        interval = cuts[grade].get(parameter)
        if interval is not None and interval[0] <= value <= interval[1]:
            return grade
    return "NK"


def fake_hit_rate_grade(
    parameters: dict[str, Any],
    cuts: dict[str, dict[str, list[float]]],
) -> str | None:
    """Classify the two-stage FakeHitRate result as one ALPIDE test grade."""
    ten_parameter = "FakeHitRate.fakerate-10masked"
    hundred_parameter = "FakeHitRate.fakerate-100masked"
    ten_value = parameters.get(ten_parameter)
    hundred_value = parameters.get(hundred_parameter)

    has_ten = is_numeric(ten_value)
    has_hundred = is_numeric(hundred_value)
    if not has_ten and not has_hundred:
        return None

    gold_cut = cuts["GOLD"].get(ten_parameter)
    if (
        has_ten
        and gold_cut is not None
        and gold_cut[0] <= float(ten_value) <= gold_cut[1]
    ):
        return "GOLD"

    for grade in ("SILVER", "BRONZE"):
        interval = cuts[grade].get(hundred_parameter)
        if (
            has_hundred
            and interval is not None
            and interval[0] <= float(hundred_value) <= interval[1]
        ):
            return grade
    return "NK"


def individual_fake_hit_rate_grade(
    parameter: str,
    value: float,
    cuts: dict[str, dict[str, list[float]]],
) -> str:
    """Grade one FakeHitRate measurement for its own ALPIDE-style plot."""
    if parameter == "FakeHitRate.fakerate-10masked":
        interval = cuts["GOLD"].get(parameter)
        if interval is not None and interval[0] <= value <= interval[1]:
            return "GOLD"
        # The ALPIDE reference and the previous ALTAI ROOT plot show chips that
        # fail the 10-masked Gold cut in Silver while their final grade is
        # deferred to the 100-masked measurement.  This is display semantics,
        # not the final combined FakeHitRate classification.
        if 0.0 <= value <= 1.0e-3:
            return "SILVER"
        return "NK"

    if parameter == "FakeHitRate.fakerate-100masked":
        for grade in ("SILVER", "BRONZE"):
            interval = cuts[grade].get(parameter)
            if interval is not None and interval[0] <= value <= interval[1]:
                return grade
        return "NK"

    raise ValueError(f"Not an individual FakeHitRate parameter: {parameter}")


def plot_value_grade(
    parameter: str,
    value: float,
    cuts: dict[str, dict[str, list[float]]],
) -> str:
    """Grade a raw value for the parameter's individual distribution."""
    if parameter in FAKE_HIT_RATE_PARAMETERS:
        return individual_fake_hit_rate_grade(parameter, value, cuts)
    return parameter_grade(parameter, value, cuts)


def record_parameter_grade(
    record: dict[str, Any],
    parameter: str,
    cuts: dict[str, dict[str, list[float]]],
) -> str | None:
    if parameter in FAKE_HIT_RATE_PARAMETERS:
        return fake_hit_rate_grade(record["params"], cuts)
    value = record["params"].get(parameter)
    if not is_numeric(value):
        return None
    return parameter_grade(parameter, float(value), cuts)


def selected_specs(pilot: bool) -> list[PlotSpec]:
    if not pilot:
        return list(PLOT_SPECS)
    return [
        spec
        for spec in PLOT_SPECS
        if spec.parameter in PILOT_PARAMETERS
    ]


def collect_plot_data(
    records: list[dict[str, Any]],
    specs: list[PlotSpec],
    cuts: dict[str, dict[str, list[float]]],
) -> dict[str, dict[str, Any]]:
    contact_fail = sum(
        record["status"] == "CONTACT_FAIL"
        for record in records
    )
    output: dict[str, dict[str, Any]] = {}
    for spec in specs:
        entries = []
        for record in records:
            if record["status"] == "CONTACT_FAIL":
                continue
            value = record["params"].get(spec.parameter)
            if not is_numeric(value):
                continue
            numeric_value = float(value)
            entries.append(
                {
                    "value": numeric_value,
                    "grade": plot_value_grade(
                        spec.parameter,
                        numeric_value,
                        cuts,
                    ),
                    "combined_fake_hit_rate_grade": (
                        fake_hit_rate_grade(record["params"], cuts)
                        if spec.parameter in FAKE_HIT_RATE_PARAMETERS
                        else None
                    ),
                }
            )
        values = [entry["value"] for entry in entries]
        output[spec.parameter] = {
            "entries": entries,
            "values": values,
            "measured": len(values),
            "contact_fail": contact_fail,
            "missing_not_contact_fail": sum(
                record["status"] != "CONTACT_FAIL"
                and not is_numeric(record["params"].get(spec.parameter))
                for record in records
            ),
        }
    return output


def print_data_summary(
    records: list[dict[str, Any]],
    specs: list[PlotSpec],
    plot_data: dict[str, dict[str, Any]],
    criteria_version: int | None,
    scope_label: str = "cumulative",
) -> None:
    contact_fail = sum(
        record["status"] == "CONTACT_FAIL"
        for record in records
    )
    print(f"Dataset: {scope_label}")
    print(f"Classification version: {criteria_version}")
    print(f"Latest unique chips: {len(records)}")
    print(f"Contact fail: {contact_fail}")
    print(f"Plots: {len(specs) + 1} ({len(specs)} distributions + 1 summary)")
    for spec in specs:
        summary = plot_data[spec.parameter]
        print(
            f"  {spec.parameter}: measured={summary['measured']}, "
            f"missing={summary['missing_not_contact_fail']}"
        )


def import_root():
    try:
        import ROOT  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyROOT is not installed in the active environment. "
            "Activate altai-chiptest and install ROOT before creating plots."
        ) from exc
    ROOT.gROOT.SetBatch(True)
    return ROOT


def configure_root_style(ROOT) -> dict[str, int]:
    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetOptTitle(0)
    ROOT.gStyle.SetCanvasColor(ROOT.kWhite)
    ROOT.gStyle.SetPadColor(ROOT.kWhite)
    ROOT.gStyle.SetFrameFillColor(ROOT.kWhite)
    ROOT.gStyle.SetLegendBorderSize(1)
    ROOT.gStyle.SetLegendFillColor(ROOT.kWhite)
    ROOT.gStyle.SetTextFont(42)
    ROOT.gStyle.SetLabelFont(42, "XYZ")
    ROOT.gStyle.SetTitleFont(42, "XYZ")
    return {
        grade: ROOT.TColor.GetColor(*rgb)
        for grade, rgb in ALPIDE_COLORS.items()
    }


def log_edges(spec: PlotSpec) -> array:
    start = math.log10(spec.x_min)
    stop = math.log10(spec.x_max)
    step = (stop - start) / spec.bins
    return array(
        "d",
        [10.0 ** (start + step * index) for index in range(spec.bins + 1)],
    )


def new_histogram(ROOT, name: str, spec: PlotSpec):
    if spec.log_x:
        histogram = ROOT.TH1D(name, "", spec.bins, log_edges(spec))
    else:
        histogram = ROOT.TH1D(
            name,
            "",
            spec.bins,
            spec.x_min,
            spec.x_max,
        )
    histogram.SetDirectory(0)
    return histogram


def padded_axis_range(spec: PlotSpec) -> tuple[float, float]:
    """Return ALPIDE-style display limits without changing data binning."""
    if spec.log_x:
        return (
            spec.x_min / LOG_AXIS_PADDING_FACTOR,
            spec.x_max * LOG_AXIS_PADDING_FACTOR,
        )
    padding = (
        spec.x_max - spec.x_min
    ) * LINEAR_AXIS_PADDING_FRACTION
    return spec.x_min - padding, spec.x_max + padding


def displayed_value(value: float, spec: PlotSpec) -> tuple[float, str | None]:
    """Keep every measured value visible without changing its raw-value grade."""
    relative_epsilon = 1.0e-6
    if spec.log_x:
        if value <= 0:
            return spec.x_min * (1.0 + relative_epsilon), "zero_to_first_bin"
        if value < spec.x_min:
            return spec.x_min * (1.0 + relative_epsilon), "below_min_to_first_bin"
        if value >= spec.x_max:
            adjustment = (
                "above_max_to_last_bin"
                if value > spec.x_max
                else "upper_edge_to_last_bin"
            )
            return spec.x_max / (1.0 + relative_epsilon), adjustment
        return value, None

    epsilon = max(abs(spec.x_max - spec.x_min), 1.0) * 1.0e-9
    if value < spec.x_min:
        return spec.x_min + epsilon, "below_min_to_first_bin"
    if value >= spec.x_max:
        adjustment = (
            "above_max_to_last_bin"
            if value > spec.x_max
            else "upper_edge_to_last_bin"
        )
        return spec.x_max - epsilon, adjustment
    return value, None


def interval_label(low: float, high: float) -> str:
    return f"[{low:g}, {high:g}]"


def cumulative_fraction(
    values: list[float],
    interval: list[float],
) -> float:
    if not values:
        return 0.0
    passed = sum(interval[0] <= value <= interval[1] for value in values)
    return passed / len(values)


def robust_fit_range(values: list[float], spec: PlotSpec) -> tuple[float, float]:
    visible = [
        value
        for value in values
        if spec.x_min <= value <= spec.x_max
    ]
    if len(visible) < 5:
        return spec.x_min, spec.x_max
    median = statistics.median(visible)
    mad = statistics.median(abs(value - median) for value in visible)
    sigma = 1.4826 * mad
    if sigma <= 0:
        sigma = statistics.pstdev(visible)
    if sigma <= 0:
        return spec.x_min, spec.x_max
    return (
        max(spec.x_min, median - 3.0 * sigma),
        min(spec.x_max, median + 3.0 * sigma),
    )


def add_missing_annotation(
    ROOT,
    contact_fail: int,
    missing: int,
    start_y: float = 0.625,
):
    lines = []
    for y_position, text in (
        (start_y, f"Contact fail: {contact_fail} (not plotted)"),
        (start_y - 0.04, f"Missing: {missing} (not plotted)"),
    ):
        # Use a separate TLatex object for each line.  Reusing DrawLatex from
        # one PyROOT proxy can corrupt one string when a logarithmic pad is
        # repainted during SaveAs.
        line = ROOT.TLatex(0.62, y_position, text)
        line.SetNDC(True)
        line.SetTextFont(42)
        line.SetTextSize(0.027)
        line.SetTextColor(ROOT.kBlack)
        line.Draw()
        lines.append(line)
    return lines


def add_edge_annotation(
    ROOT,
    spec: PlotSpec,
    adjustments: dict[str, int],
):
    lines = []
    descriptions = []
    below = adjustments["below_min_to_first_bin"]
    above = adjustments["above_max_to_last_bin"]
    if below:
        descriptions.append(
            f"< {spec.x_min:g}: {below} (shown in first bin)"
        )
    if above:
        descriptions.append(
            f"> {spec.x_max:g}: {above} (shown in last bin)"
        )
    for index, description in enumerate(descriptions):
        line = ROOT.TLatex(0.62, 0.655 - 0.04 * index, description)
        line.SetNDC(True)
        line.SetTextFont(42)
        line.SetTextSize(0.024)
        line.SetTextColor(ROOT.kBlack)
        line.Draw()
        lines.append(line)
    return lines


def display_bin_grade(
    spec: PlotSpec,
    bin_index: int,
    bin_center: float,
    cuts: dict[str, dict[str, list[float]]],
    edge_grade_overrides: dict[int, str] | None = None,
) -> str:
    """Choose one ALPIDE-style display color for a complete histogram bin."""
    # PowerTest.i_d has many measured outliers outside its ALPIDE reference
    # x-range.  They are clamped into the visible edge bins, but their original
    # unanimous raw-value grade must take precedence over the edge-bin center.
    # Otherwise the <35 mA NK population is misleadingly painted Bronze
    # because the first bin center is about 35.25 mA.
    if edge_grade_overrides and bin_index in edge_grade_overrides:
        return edge_grade_overrides[bin_index]
    # The broad first bin in the pixel-count plots represents the best
    # near-zero population.  The ALPIDE reference renders that whole bar Gold.
    if spec.parameter in PIXEL_COUNT_PARAMETERS and bin_index == 1:
        return "GOLD"
    return plot_value_grade(spec.parameter, bin_center, cuts)


def linear_major_values(
    minimum: float,
    maximum: float,
    step: float,
) -> list[float]:
    first = math.ceil((minimum - abs(step) * 1.0e-9) / step)
    last = math.floor((maximum + abs(step) * 1.0e-9) / step)
    return [index * step for index in range(first, last + 1)]


def logarithmic_major_values(
    minimum: float,
    maximum: float,
) -> list[float]:
    first = math.ceil(math.log10(minimum) - 1.0e-9)
    last = math.floor(math.log10(maximum) + 1.0e-9)
    return [10.0 ** exponent for exponent in range(first, last + 1)]


def nice_linear_step(minimum: float, maximum: float, target: int = 5) -> float:
    raw_step = max((maximum - minimum) / target, 1.0e-12)
    magnitude = 10.0 ** math.floor(math.log10(raw_step))
    candidates = [
        factor * magnitude
        for factor in (1.0, 2.0, 5.0, 10.0)
    ]
    return min(
        candidates,
        key=lambda candidate: abs(math.log(candidate / raw_step)),
    )


def format_major_label(value: float, step: float | None = None) -> str:
    if abs(value) < 1.0e-12:
        value = 0.0
    if step is None or step >= 1.0:
        if math.isclose(value, round(value), abs_tol=1.0e-9):
            return str(int(round(value)))
        return f"{value:g}"
    decimals = max(1, int(math.ceil(-math.log10(step))))
    return f"{value:.{decimals}f}"


def axis_fraction(
    value: float,
    minimum: float,
    maximum: float,
    logarithmic: bool,
) -> float:
    if logarithmic:
        numerator = math.log10(value) - math.log10(minimum)
        denominator = math.log10(maximum) - math.log10(minimum)
    else:
        numerator = value - minimum
        denominator = maximum - minimum
    return numerator / denominator


def draw_manual_major_axes(
    ROOT,
    canvas,
    spec: PlotSpec,
    axis_x_min: float,
    axis_x_max: float,
    y_minimum: float,
    y_maximum: float,
):
    """Draw ALPIDE-style major ticks outward in normalized pad coordinates."""
    left = canvas.GetLeftMargin()
    right = 1.0 - canvas.GetRightMargin()
    bottom = canvas.GetBottomMargin()
    top = 1.0 - canvas.GetTopMargin()
    objects = []

    if spec.log_x:
        x_values = logarithmic_major_values(spec.x_min, spec.x_max)
        x_step = None
    else:
        if spec.x_major_step is None:
            raise ValueError(f"Missing x major step: {spec.parameter}")
        x_values = linear_major_values(
            spec.x_min,
            spec.x_max,
            spec.x_major_step,
        )
        x_step = spec.x_major_step

    for value in x_values:
        fraction = axis_fraction(
            value,
            axis_x_min,
            axis_x_max,
            spec.log_x,
        )
        x_ndc = left + fraction * (right - left)
        tick = ROOT.TLine(
            x_ndc,
            bottom,
            x_ndc,
            bottom - OUTWARD_MAJOR_TICK_LENGTH_NDC,
        )
        tick.SetNDC(True)
        tick.SetLineColor(ROOT.kBlack)
        tick.SetLineWidth(1)
        tick.Draw()
        objects.append(tick)

        label_text = (
            f"10^{{{int(round(math.log10(value)))}}}"
            if spec.log_x
            else format_major_label(value, x_step)
        )
        label = ROOT.TLatex(
            x_ndc,
            bottom - OUTWARD_MAJOR_TICK_LENGTH_NDC - 0.007,
            label_text,
        )
        label.SetNDC(True)
        label.SetTextAlign(23)
        label.SetTextFont(42)
        label.SetTextSize(0.038)
        label.SetTextColor(ROOT.kBlack)
        label.Draw()
        objects.append(label)

    if spec.log_y:
        y_values = logarithmic_major_values(y_minimum, y_maximum)
        y_step = None
    else:
        y_step = nice_linear_step(y_minimum, y_maximum)
        y_values = linear_major_values(y_minimum, y_maximum, y_step)

    for value in y_values:
        fraction = axis_fraction(
            value,
            y_minimum,
            y_maximum,
            spec.log_y,
        )
        y_ndc = bottom + fraction * (top - bottom)
        tick = ROOT.TLine(
            left,
            y_ndc,
            left - OUTWARD_MAJOR_TICK_LENGTH_NDC,
            y_ndc,
        )
        tick.SetNDC(True)
        tick.SetLineColor(ROOT.kBlack)
        tick.SetLineWidth(1)
        tick.Draw()
        objects.append(tick)

        label_text = (
            f"10^{{{int(round(math.log10(value)))}}}"
            if spec.log_y
            else format_major_label(value, y_step)
        )
        label = ROOT.TLatex(
            left - OUTWARD_MAJOR_TICK_LENGTH_NDC - 0.006,
            y_ndc,
            label_text,
        )
        label.SetNDC(True)
        label.SetTextAlign(32)
        label.SetTextFont(42)
        label.SetTextSize(0.038)
        label.SetTextColor(ROOT.kBlack)
        label.Draw()
        objects.append(label)

    x_title = ROOT.TLatex(0.5 * (left + right), 0.032, spec.x_title)
    x_title.SetNDC(True)
    x_title.SetTextAlign(22)
    x_title.SetTextFont(42)
    x_title.SetTextSize(0.045)
    x_title.SetTextColor(ROOT.kBlack)
    x_title.Draw()
    objects.append(x_title)

    y_title = ROOT.TLatex(0.030, 0.5 * (bottom + top), "Number of chips")
    y_title.SetNDC(True)
    y_title.SetTextAlign(22)
    y_title.SetTextAngle(90.0)
    y_title.SetTextFont(42)
    y_title.SetTextSize(0.045)
    y_title.SetTextColor(ROOT.kBlack)
    y_title.Draw()
    objects.append(y_title)
    return objects


def draw_summary_major_x_axis(ROOT, canvas, x_max: float):
    """Draw the summary count axis with major-only outward ticks."""
    left = canvas.GetLeftMargin()
    right = 1.0 - canvas.GetRightMargin()
    bottom = canvas.GetBottomMargin()
    objects = []
    for value in linear_major_values(0.0, x_max, 50.0):
        fraction = value / x_max if x_max else 0.0
        x_ndc = left + fraction * (right - left)
        tick = ROOT.TLine(
            x_ndc,
            bottom,
            x_ndc,
            bottom - OUTWARD_MAJOR_TICK_LENGTH_NDC,
        )
        tick.SetNDC(True)
        tick.SetLineColor(ROOT.kBlack)
        tick.SetLineWidth(1)
        tick.Draw()
        objects.append(tick)

        label = ROOT.TLatex(
            x_ndc,
            bottom - OUTWARD_MAJOR_TICK_LENGTH_NDC - 0.007,
            format_major_label(value, 50.0),
        )
        label.SetNDC(True)
        label.SetTextAlign(23)
        label.SetTextFont(42)
        label.SetTextSize(0.033)
        label.SetTextColor(ROOT.kBlack)
        label.Draw()
        objects.append(label)

    x_title = ROOT.TLatex(
        0.5 * (left + right),
        0.025,
        "Number of chips",
    )
    x_title.SetNDC(True)
    x_title.SetTextAlign(22)
    x_title.SetTextFont(42)
    x_title.SetTextSize(0.045)
    x_title.SetTextColor(ROOT.kBlack)
    x_title.Draw()
    objects.append(x_title)
    return objects


def draw_plot(
    ROOT,
    root_file,
    spec: PlotSpec,
    summary: dict[str, Any],
    cuts: dict[str, dict[str, list[float]]],
    colors: dict[str, int],
    output_dir: Path,
    save_pdf: bool,
    annotate_missing: bool,
    object_prefix: str = "",
) -> dict[str, Any]:
    values: list[float] = summary["values"]
    base_name = spec.filename.replace("-", "_")
    safe_name = (
        f"{object_prefix}_{base_name}"
        if object_prefix
        else base_name
    )

    canvas = ROOT.TCanvas(
        f"canvas_{safe_name}",
        "",
        762,
        454,
    )
    canvas.SetLeftMargin(0.115)
    canvas.SetRightMargin(0.035)
    canvas.SetTopMargin(0.04)
    canvas.SetBottomMargin(0.13)
    # Match the PDF/Matplotlib appearance: ticks only on the bottom and left.
    canvas.SetTicks(0, 0)
    canvas.SetLogx(spec.log_x)
    canvas.SetLogy(spec.log_y)

    histograms = {
        grade: new_histogram(
            ROOT,
            f"hist_{safe_name}_{grade.lower()}",
            spec,
        )
        for grade in DISPLAY_GRADES
    }
    total_hist = new_histogram(ROOT, f"hist_{safe_name}_all", spec)

    exact_value_counts = {grade: 0 for grade in DISPLAY_GRADES}
    combined_fake_hit_rate_counts = {
        grade: 0 for grade in DISPLAY_GRADES
    }
    adjustments = {
        "zero_to_first_bin": 0,
        "below_min_to_first_bin": 0,
        "upper_edge_to_last_bin": 0,
        "above_max_to_last_bin": 0,
    }
    adjustment_grade_counts = {
        adjustment: {grade: 0 for grade in DISPLAY_GRADES}
        for adjustment in adjustments
    }
    for entry in summary["entries"]:
        value = entry["value"]
        grade = entry["grade"]
        draw_value, adjustment = displayed_value(value, spec)
        if adjustment is not None:
            adjustments[adjustment] += 1
            adjustment_grade_counts[adjustment][grade] += 1
        total_hist.Fill(draw_value)
        exact_value_counts[grade] += 1
        combined_grade = entry["combined_fake_hit_rate_grade"]
        if combined_grade is not None:
            combined_fake_hit_rate_counts[combined_grade] += 1

    edge_grade_overrides: dict[int, str] = {}
    if spec.parameter == "PowerTest.i_d":
        edge_adjustments = {
            1: ("below_min_to_first_bin",),
            total_hist.GetNbinsX(): (
                "upper_edge_to_last_bin",
                "above_max_to_last_bin",
            ),
        }
        for bin_index, adjustment_names in edge_adjustments.items():
            grades = {
                grade
                for adjustment_name in adjustment_names
                for grade, count in adjustment_grade_counts[
                    adjustment_name
                ].items()
                if count > 0
            }
            # Preserve the raw grade only when all values moved into that edge
            # agree.  This keeps the one-color-per-bin ALPIDE presentation
            # honest without inventing a grade for a mixed future dataset.
            if len(grades) == 1:
                edge_grade_overrides[bin_index] = grades.pop()

    # Match the ALPIDE/PDF rendering: color the complete x-bin from its center
    # instead of stacking differently graded chips inside the same vertical bar.
    # Exact chip-by-chip counts above remain independent of this display choice.
    display_bin_counts = {grade: 0 for grade in DISPLAY_GRADES}
    for bin_index in range(1, total_hist.GetNbinsX() + 1):
        content = total_hist.GetBinContent(bin_index)
        if content <= 0:
            continue
        grade = display_bin_grade(
            spec,
            bin_index,
            total_hist.GetBinCenter(bin_index),
            cuts,
            edge_grade_overrides,
        )
        histogram = histograms[grade]
        histogram.SetBinContent(bin_index, content)
        histogram.SetBinError(bin_index, total_hist.GetBinError(bin_index))
        display_bin_counts[grade] += int(round(content))

    stack = ROOT.THStack(f"stack_{safe_name}", "")
    for grade in DISPLAY_GRADES:
        histogram = histograms[grade]
        histogram.SetFillColor(colors[grade])
        histogram.SetLineColor(colors[grade])
        histogram.SetLineWidth(1)
        stack.Add(histogram)

    if spec.log_y:
        y_minimum = 0.7
        content_maximum = max(1.0, total_hist.GetMaximum())
        decade_ceiling = 10.0 ** math.ceil(math.log10(content_maximum))
        y_maximum = max(10.0, decade_ceiling * 1.15)
    else:
        y_minimum = 0.0
        y_maximum = max(1.0, total_hist.GetMaximum() * 1.18)

    axis_x_min, axis_x_max = padded_axis_range(spec)
    axis_histogram = ROOT.TH1D(
        f"axis_{safe_name}",
        "",
        1,
        axis_x_min,
        axis_x_max,
    )
    axis_histogram.SetDirectory(0)
    axis_histogram.SetMinimum(y_minimum)
    axis_histogram.SetMaximum(y_maximum)
    # Draw only the rectangular frame here. Labels, titles, and outward major
    # ticks are added explicitly in NDC coordinates after the data are drawn.
    for axis in (
        axis_histogram.GetXaxis(),
        axis_histogram.GetYaxis(),
    ):
        axis.SetLabelSize(0.0)
        axis.SetTitleSize(0.0)
        axis.SetTickLength(0.0)
    axis_histogram.Draw("AXIS")

    # The axis-only frame adds the ALPIDE whitespace while the overlaid grade
    # histograms retain their original edges and therefore their original bins.
    # Drawing THStack with SAME on a wider frame is unstable in some PyROOT
    # builds; the grade histograms are mutually exclusive by bin, so drawing
    # them individually is visually identical and avoids that ROOT crash.
    stack.SetMinimum(y_minimum)
    stack.SetMaximum(y_maximum)
    for grade in DISPLAY_GRADES:
        histograms[grade].Draw("HIST SAME")
    # Force the stack and logarithmic-axis repaint to finish before drawing
    # labels.  Otherwise ROOT may lazily repaint the stack over TLatex text.
    canvas.Modified()
    canvas.Update()

    legend = ROOT.TLegend(0.62, 0.69, 0.955, 0.955)
    legend.SetTextFont(42)
    legend.SetTextSize(0.027)
    legend.SetFillColor(ROOT.kWhite)
    legend.SetFillStyle(1001)
    legend.SetBorderSize(1)
    legend.SetLineColor(ROOT.TColor.GetColor(190, 190, 190))

    gaussian = None
    fit_result = None
    if spec.gaussian and len(values) >= 5 and total_hist.GetEntries() >= 5:
        fit_low, fit_high = robust_fit_range(values, spec)
        gaussian = ROOT.TF1(
            f"gaussian_{safe_name}",
            "gaus",
            fit_low,
            fit_high,
        )
        gaussian.SetLineColor(ROOT.kBlack)
        gaussian.SetLineWidth(2)
        total_hist.Fit(gaussian, "Q0R")
        gaussian.Draw("SAME")
        mean = gaussian.GetParameter(1)
        sigma = abs(gaussian.GetParameter(2))
        fit_result = {
            "mean": float(mean),
            "sigma": float(sigma),
            "fit_low": fit_low,
            "fit_high": fit_high,
        }
        legend.AddEntry(
            gaussian,
            f"Gaussian (#mu = {mean:.2f}, #sigma = {sigma:.2f})",
            "l",
        )

    if spec.parameter in FAKE_HIT_RATE_PARAMETERS:
        total = len(values)
        legend_grades = (
            ("NK", "SILVER", "GOLD")
            if spec.parameter.endswith("10masked")
            else ("NK", "BRONZE", "SILVER")
        )
        for grade in legend_grades:
            count = exact_value_counts[grade]
            fraction = count / total if total else 0.0
            label = "NOK" if grade == "NK" else grade.title()
            legend.AddEntry(
                histograms[grade],
                f"{label} : {count} ({fraction:.2f})",
                "f",
            )
    else:
        legend.AddEntry(histograms["NK"], "NOK", "f")
        for grade in ("BRONZE", "SILVER", "GOLD"):
            interval = cuts[grade].get(spec.parameter)
            if interval is None:
                continue
            fraction = cumulative_fraction(values, interval)
            legend.AddEntry(
                histograms[grade],
                f"{interval_label(*interval)} : {fraction:.2f}",
                "f",
            )
    canvas.RedrawAxis()
    axis_objects = draw_manual_major_axes(
        ROOT,
        canvas,
        spec,
        axis_x_min,
        axis_x_max,
        y_minimum,
        y_maximum,
    )
    legend.Draw()

    annotations = []
    annotations.extend(add_edge_annotation(ROOT, spec, adjustments))
    if annotate_missing:
        annotations.extend(
            add_missing_annotation(
                ROOT,
                summary["contact_fail"],
                summary["missing_not_contact_fail"],
                start_y=0.625 - 0.04 * len(annotations),
            )
        )
    canvas.Modified()
    canvas.Update()

    png_path = output_dir / f"{spec.filename}.png"
    canvas.SaveAs(str(png_path))
    pdf_path = None
    if save_pdf:
        pdf_path = output_dir / f"{spec.filename}.pdf"
        canvas.SaveAs(str(pdf_path))

    root_directory = root_file.GetDirectory(spec.group)
    if not root_directory:
        root_directory = root_file.mkdir(spec.group)
    root_directory.cd()
    for histogram in histograms.values():
        histogram.Write()
    total_hist.Write()
    axis_histogram.Write()
    stack.Write()
    if gaussian is not None:
        gaussian.Write()
    canvas.Write()
    root_file.cd()

    # Keep ROOT-owned objects alive until canvas output and ROOT-file writes end.
    canvas._plot_objects = [
        *histograms.values(),
        total_hist,
        axis_histogram,
        stack,
        *axis_objects,
        legend,
        *annotations,
        gaussian,
    ]

    return {
        "parameter": spec.parameter,
        "png": str(png_path.relative_to(output_dir)),
        "pdf": (
            str(pdf_path.relative_to(output_dir))
            if pdf_path is not None
            else None
        ),
        "measured": summary["measured"],
        "contact_fail": summary["contact_fail"],
        "missing_not_contact_fail": summary["missing_not_contact_fail"],
        "exclusive_grade_counts": exact_value_counts,
        "exact_value_grade_counts": exact_value_counts,
        "display_bin_grade_counts": display_bin_counts,
        "combined_fake_hit_rate_grade_counts": (
            combined_fake_hit_rate_counts
            if spec.parameter in FAKE_HIT_RATE_PARAMETERS
            else None
        ),
        "display_adjustments": adjustments,
        "display_adjustment_grade_counts": adjustment_grade_counts,
        "edge_bin_grade_overrides": {
            str(bin_index): grade
            for bin_index, grade in edge_grade_overrides.items()
        },
        "display_axis_range": [axis_x_min, axis_x_max],
        "gaussian_fit": fit_result,
    }


def collect_summary_counts(
    records: list[dict[str, Any]],
    cuts: dict[str, dict[str, list[float]]],
) -> list[dict[str, Any]]:
    summaries = []
    for parameter, label in SUMMARY_PARAMETERS:
        counts = {grade: 0 for grade in DISPLAY_GRADES}
        measured = 0
        for record in records:
            if record["status"] == "CONTACT_FAIL":
                continue
            if parameter == FAKE_HIT_RATE_SUMMARY_PARAMETER:
                grade = fake_hit_rate_grade(record["params"], cuts)
            else:
                grade = record_parameter_grade(record, parameter, cuts)
            if grade is not None:
                measured += 1
                counts[grade] += 1
        summaries.append(
            {
                "parameter": parameter,
                "label": label,
                "measured": measured,
                "exclusive_grade_counts": counts,
            }
        )
    return summaries


def draw_summary_plot(
    ROOT,
    root_file,
    records: list[dict[str, Any]],
    cuts: dict[str, dict[str, list[float]]],
    colors: dict[str, int],
    output_dir: Path,
    save_pdf: bool,
    object_prefix: str = "",
) -> dict[str, Any]:
    """Draw the 17th PPT graph: all-parameter horizontal grade counts."""
    summaries = collect_summary_counts(records, cuts)
    maximum_count = max(
        (summary["measured"] for summary in summaries),
        default=0,
    )
    x_max = max(300, int(math.ceil((maximum_count + 1) / 50.0) * 50))
    row_count = len(summaries)

    summary_name = (
        f"{object_prefix}_parameter_grade_counts"
        if object_prefix
        else "parameter_grade_counts"
    )
    canvas = ROOT.TCanvas(
        f"canvas_{summary_name}",
        "",
        910,
        542,
    )
    canvas.SetLeftMargin(0.265)
    canvas.SetRightMargin(0.025)
    canvas.SetTopMargin(0.065)
    canvas.SetBottomMargin(0.11)
    canvas.SetTicks(0, 0)

    frame = ROOT.TH2D(
        f"summary_{summary_name}_frame",
        "",
        1,
        0.0,
        float(x_max),
        row_count,
        0.0,
        float(row_count),
    )
    frame.SetDirectory(0)
    frame.GetXaxis().SetTitleSize(0.0)
    frame.GetXaxis().SetLabelSize(0.0)
    frame.GetXaxis().SetTickLength(0.0)
    frame.GetYaxis().SetLabelSize(0.021)
    frame.GetYaxis().SetTickLength(0.0)
    for index, summary in enumerate(summaries, start=1):
        frame.GetYaxis().SetBinLabel(index, summary["label"])
    frame.Draw("AXIS")

    boxes = []
    for row_index, summary in enumerate(summaries):
        left = 0.0
        for grade in DISPLAY_GRADES:
            count = summary["exclusive_grade_counts"][grade]
            if count <= 0:
                continue
            box = ROOT.TBox(
                left,
                row_index + 0.12,
                left + count,
                row_index + 0.88,
            )
            box.SetFillColor(colors[grade])
            box.SetLineColor(colors[grade])
            box.SetLineWidth(1)
            box.Draw("SAME")
            boxes.append(box)
            left += count

    title = ROOT.TLatex(0.62, 0.965, "Classification results")
    title.SetNDC(True)
    title.SetTextAlign(22)
    title.SetTextFont(42)
    title.SetTextSize(0.031)
    title.SetTextColor(ROOT.kBlack)
    title.Draw()

    canvas.RedrawAxis()
    summary_axis_objects = draw_summary_major_x_axis(
        ROOT,
        canvas,
        float(x_max),
    )
    canvas.Modified()
    canvas.Update()

    png_path = output_dir / "Summary_parameter_grade_counts.png"
    canvas.SaveAs(str(png_path))
    pdf_path = None
    if save_pdf:
        pdf_path = output_dir / "Summary_parameter_grade_counts.pdf"
        canvas.SaveAs(str(pdf_path))

    root_directory = root_file.GetDirectory("Summary")
    if not root_directory:
        root_directory = root_file.mkdir("Summary")
    root_directory.cd()
    frame.Write()
    # The TBox/TLatex primitives are serialized as part of the canvas.
    canvas.Write()
    root_file.cd()

    canvas._plot_objects = [
        frame,
        *boxes,
        title,
        *summary_axis_objects,
    ]
    return {
        "parameter": "SUMMARY",
        "png": str(png_path.relative_to(output_dir)),
        "pdf": (
            str(pdf_path.relative_to(output_dir))
            if pdf_path is not None
            else None
        ),
        "parameter_count": len(summaries),
        "parameters": summaries,
    }


def write_manifest(
    output_dir: Path,
    run_id: str,
    dataset_scope: str,
    root_filename: str,
    records: list[dict[str, Any]],
    specs: list[PlotSpec],
    plot_results: list[dict[str, Any]],
    criteria_version: int | None,
    pilot: bool,
    annotate_missing: bool,
    batch_output_folders: list[str] | None = None,
) -> None:
    batches = sorted({record["batch"] for record in records})
    status_counts: dict[str, int] = {}
    for record in records:
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    manifest = {
        "run_id": run_id,
        "dataset_scope": dataset_scope,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "testdata_root": str(TESTDATA_ROOT),
        "source_batches": batches,
        "selection": (
            "latest run per corrected physical Chip ID across all testdata "
            "batches"
            if dataset_scope == "cumulative"
            else (
                "latest run per corrected physical Chip ID within "
                f"{dataset_scope}"
            )
        ),
        "criteria_version": criteria_version,
        "criteria_note": (
            "ALTAI criteria; PowerTest.i_d boundaries include the -4.4 mA shift."
        ),
        "pilot": pilot,
        "graph_count": len(plot_results),
        "root_file": root_filename,
        "batch_output_folders": batch_output_folders or [],
        "output_layout": (
            "Cumulative PNG/PDF files are stored directly in the run folder; "
            "each testdata batch has the same output set in its named "
            "subfolder."
            if dataset_scope == "cumulative"
            else (
                "This testdata batch's PNG/PDF files are stored directly in "
                "its named subfolder."
            )
        ),
        "chip_count": len(records),
        "status_counts": status_counts,
        "contact_fail_policy": (
            "Contact-fail chips are reported separately and are not inserted "
            "into numeric histogram bins."
        ),
        "missing_policy": (
            "Non-contact-fail chips without a numeric parameter value are "
            "reported separately and are not inserted into histogram bins."
        ),
        "missing_annotation_visible": annotate_missing,
        "style": {
            "reference": (
                "ALPIDE_series_mass_testing_and_classification.pdf"
            ),
            "canvas_pixels": [762, 454],
            "summary_canvas_pixels": [910, 542],
            "colors_rgb": ALPIDE_COLORS,
            "legend_fractions": (
                "Cumulative pass fraction for ordinary parameters; exclusive "
                "raw-value count and fraction for each individual FakeHitRate "
                "distribution."
            ),
            "fake_hit_rate_grade": (
                "The 10masked distribution follows the ALPIDE display: GOLD "
                "passes its cut, SILVER marks values up to 1e-3 that proceed "
                "to the 100masked evaluation, and larger values are NK. The "
                "100masked distribution determines SILVER, BRONZE, or NK. "
                "Only the summary uses the final combined two-stage grade: "
                "10masked determines GOLD; otherwise 100masked determines "
                "SILVER, BRONZE, or NK."
            ),
            "edge_value_policy": (
                "Values outside the visible x-range are drawn in the first or "
                "last visible bin. For PowerTest.i_d, an edge bin keeps the "
                "raw-value grade when all values clamped to that edge have the "
                "same grade; this prevents NK outliers from being recolored by "
                "the bin center. Exact raw-value grade counts remain in the "
                "manifest independently of display-bin coloring."
            ),
            "distribution_bin_color_policy": (
                "ALPIDE/PDF style: each complete x-bin receives one color from "
                "its bin-center grade, so a vertical bar never mixes colors. "
                "The first bin of analogue/digital pixel-count plots is Gold "
                "to represent the near-zero best population."
            ),
            "x_axis_padding_policy": (
                "Data histogram limits and bins are unchanged. The visible "
                "linear x-axis extends by 3 percent on each side; logarithmic "
                "FakeHitRate axes extend by a factor of 1.25 on each side."
            ),
            "tick_policy": (
                "Only parameter-specific major ticks are drawn on the bottom "
                "and left axes. Tick lines and labels are placed explicitly "
                "outside the data frame; secondary and tertiary ticks are "
                "not drawn."
            ),
        },
        "plot_specs": [asdict(spec) for spec in specs],
        "summary_parameters": [
            {"parameter": parameter, "label": label}
            for parameter, label in SUMMARY_PARAMETERS
        ],
        "plots": plot_results,
    }
    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def generate_plot_set(
    ROOT,
    colors: dict[str, int],
    output_dir: Path,
    run_id: str,
    dataset_scope: str,
    object_prefix: str,
    root_filename: str,
    records: list[dict[str, Any]],
    specs: list[PlotSpec],
    plot_data: dict[str, dict[str, Any]],
    cuts: dict[str, dict[str, list[float]]],
    criteria_version: int | None,
    pilot: bool,
    save_pdf: bool,
    annotate_missing: bool,
    batch_output_folders: list[str] | None = None,
) -> None:
    """Create one complete ROOT/PNG/manifest output set."""
    output_dir.mkdir(parents=True, exist_ok=False)
    root_path = output_dir / root_filename
    root_file = ROOT.TFile(str(root_path), "RECREATE")
    if not root_file or root_file.IsZombie():
        raise RuntimeError(f"Cannot create ROOT file: {root_path}")

    plot_results: list[dict[str, Any]] = []
    try:
        for spec in specs:
            print(f"[{dataset_scope}] Creating {spec.parameter} ...")
            result = draw_plot(
                ROOT,
                root_file,
                spec,
                plot_data[spec.parameter],
                cuts,
                colors,
                output_dir,
                save_pdf=save_pdf,
                annotate_missing=annotate_missing,
                object_prefix=object_prefix,
            )
            plot_results.append(result)
        print(
            f"[{dataset_scope}] Creating all-parameter "
            "grade-count summary ..."
        )
        plot_results.append(
            draw_summary_plot(
                ROOT,
                root_file,
                records,
                cuts,
                colors,
                output_dir,
                save_pdf=save_pdf,
                object_prefix=object_prefix,
            )
        )
        root_file.Write()
    finally:
        root_file.Close()

    write_manifest(
        output_dir,
        run_id,
        dataset_scope,
        root_filename,
        records,
        specs,
        plot_results,
        criteria_version,
        pilot,
        annotate_missing,
        batch_output_folders=batch_output_folders,
    )


def main() -> int:
    args = parse_args()
    validate_project_layout()
    run_id = validate_run_id(args.run_id)
    specs = selected_specs(args.pilot)

    cuts, criteria_version = load_criteria()
    all_records = collect_records()
    cumulative_records = add_grades(
        latest_per_chip(all_records),
        cuts,
    )
    batch_records = build_batch_records(all_records, cuts)
    dataset_records = {
        "cumulative": cumulative_records,
        **{
            batch_name: batch_records[batch_name]
            for batch_name in sorted(batch_records, reverse=True)
        },
    }
    dataset_plot_data = {
        scope: collect_plot_data(records, specs, cuts)
        for scope, records in dataset_records.items()
    }

    print(f"Project: {PROJECT_ROOT}")
    print(f"Testdata: {TESTDATA_ROOT}")
    print(f"Output sets: {len(dataset_records)}")
    for scope, records in dataset_records.items():
        print_data_summary(
            records,
            specs,
            dataset_plot_data[scope],
            criteria_version,
            scope_label=scope,
        )
    if args.dry_run:
        print("Dry run complete; no result files were created.")
        return 0

    ROOT = import_root()
    colors = configure_root_style(ROOT)
    run_output_dir = ROOT_RESULTS / run_id
    if run_output_dir.exists():
        raise FileExistsError(
            "Output run already exists; choose another --run-id: "
            f"{run_output_dir}"
        )

    batch_names = sorted(batch_records, reverse=True)
    generate_plot_set(
        ROOT,
        colors,
        run_output_dir,
        run_id,
        "cumulative",
        "cumulative",
        f"ALTAI_{run_id}.root",
        cumulative_records,
        specs,
        dataset_plot_data["cumulative"],
        cuts,
        criteria_version,
        args.pilot,
        args.with_pdf,
        args.annotate_missing,
        batch_output_folders=batch_names,
    )
    for batch_name in batch_names:
        generate_plot_set(
            ROOT,
            colors,
            run_output_dir / batch_name,
            run_id,
            batch_name,
            batch_name,
            f"ALTAI_{batch_name}_{run_id}.root",
            batch_records[batch_name],
            specs,
            dataset_plot_data[batch_name],
            cuts,
            criteria_version,
            args.pilot,
            args.with_pdf,
            args.annotate_missing,
        )

    print(f"ROOT results created: {run_output_dir}")
    print(
        "Batch result folders: "
        + ", ".join(str(run_output_dir / name) for name in batch_names)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
