#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import glob
import argparse

import classification
from project_paths import TESTDATA_ROOT, require_testdata_path

CUT_ORDER = [
    'BackbiasIV.min_backbias_voltage',
    'SEU.seus',
    'ChipID.chip_id_errors',
    'ThresholdScanDataPortQueue.threshold_stddev',
    'DACScan.dac_tests.VCLIP.inl',
    'DACScan.dac_tests.VPULSEH.dA',
    'BackbiasIV.i_d.mean',
    'DACScan.dac_tests.ITHR.dA',
    'DACScan.dac_tests.VPULSEH.inl',
    'FIFOTest.fifo_region_errors',
    'DigitalScan.unpulsable-all',
    'DACScan.dac_tests.VPULSEL.inl',
    'AnalogueScanDataPort.num_dead_pixels0',
    'DACScan.dac_tests.IBIAS.dA',
    'BackbiasIV.i_a.max',
    'DACScan.dac_tests.IDB.dA',
    'DACScan.dac_tests.VCASN2.inl',
    'DACScan.dac_tests.VCASP.inl',
    'ThresholdScanDataPortQueue.stddev_mean_ratio',
    'Registers.errors',
    'DigitalScan.masked-all',
    'DataPort.data_port_errors',
    'DACScan.dac_tests.IDB.inl',
    'DigitalScan.bad-all',
    'FakeHitRate.fakerate-100masked',
    'AnalogueScanDataPort.num_broken_pixels0',
    'DACScan.dac_tests.VCASP.dA',
    'ThresholdScanDataPortQueue.threshold_npix',
    'DACScan.dac_tests.VCASN2.dA',
    'BackbiasIV.i_pwell.max',
    'DACScan.dac_tests.IBIAS.inl',
    'BackbiasIV.i_a.mean',
    'PowerTest.i_d',
    'PowerTest.i_a',
    'DigitalScan.stuck-all',
    'DACScan.dac_tests.VRESETD.dA',
    'DACScan.dac_tests.ITHR.inl',
    'BackbiasIV.i_pwell.3V',
    'DACScan.dac_tests.VCASN.dA',
    'DACScan.dac_tests.VCASN.inl',
    'DigitalScan.unmaskable-all',
    'AnalogueScanDataPort.num_noisy_pixels0',
    'DACScan.dac_tests.VPULSEL.dA',
    'DACScan.dac_tests.VCLIP.dA',
    'FakeHitRate.fakerate-10masked',
    'ThresholdScanDataPortQueue.threshold_mean',
    'DACScan.dac_tests.VRESETD.inl',
    'BackbiasIV.i_pwell.mean',
]


def classify_probecarddata(path, basedir=None):
    classification_information = 'Not executed.'
    classification_information, classification_parameter_cats = classification.classify_probecard_data(path)

    fields = [
        path.replace(basedir, '') if basedir else path,
        classification_information,
    ]

    for key in CUT_ORDER:
        fields.append(str(classification_parameter_cats.get(key)))

    print('\t'.join(fields))

    classification_fname = '%s/classification_output.json' % path
    with open(classification_fname, 'w') as f:
        data = {
            'version': classification.VERSION,
            'global': classification_information,
            'cuts': classification_parameter_cats
        }
        json.dump(data, f, sort_keys=True, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'PATH',
        type=str,
        nargs='+',
        help='Path of the data. Must end with CERN_PC/YYYYMMDD-HHMMSS form.'
    )
    parser.add_argument(
        '-b',
        '--basedir',
        type=str,
        help='Path of the base directory. It will be removed at the output text.'
    )
    args = parser.parse_args()

    for pathpattern in args.PATH:
        for path in glob.iglob(pathpattern):
            try:
                safe_path = require_testdata_path(path)
            except ValueError as exc:
                parser.error(str(exc))
            classify_probecarddata(str(safe_path), args.basedir)
