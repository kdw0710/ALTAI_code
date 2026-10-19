# ALTAI code

Python scripts for ALTAI chip-test data analysis, classification, cumulative reporting, and plotting.

## Repository contents

- `Scripts/analyse.py`: analysis of raw chip-test runs.
- `Scripts/classify.py`: classification of analyzed runs.
- `Scripts/make_cumulative_result_excel.py`: cumulative Excel reporting.
- `Scripts/make_*maps.py`, `Scripts/make_*trend_maps.py`, and `Scripts/make_root_plots.py`: plotting utilities.
- `Scripts/chiptests/`: test and analysis modules.
- `Scripts/classification/`: classification utilities and JSON criteria.
- `Scripts/probecard/`: probe-card support modules.

Measurement data, generated results, logs, and Python caches are excluded from this repository.

## Local data layout

The main analysis and reporting scripts use `Scripts/project_paths.py` to locate data and results relative to the repository root. Create these folders locally as needed:

```text
ALTAI_code/
├── Scripts/
├── testdata/    # local measurement data; ignored by Git
└── Results/     # generated results; ignored by Git
```

Keep the original test-run directory structure inside `testdata/`. The analysis and classification entry points reject paths outside that folder.

## Environment

Dependencies vary by script and include NumPy, Matplotlib, openpyxl, Pillow, ROOT/PyROOT, and PyUSB. Some inherited hardware and classification utilities refer to additional lab-specific modules or legacy Python interfaces. This repository preserves the source files; it does not provide a fully verified installation environment.

Use each entry point's argument parser to check its options before processing data. No measurement runs are bundled.
