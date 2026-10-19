#!/usr/bin/env python3

import os
import sys
import glob
import json
import logging
import time
import itertools
import multiprocessing as mp

from chiptests import *
from project_paths import TESTDATA_ROOT, require_testdata_path
import argparse

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

filehandler = logging.FileHandler('%s/analyse.log'%os.path.dirname(os.path.realpath(__file__)))
filehandler.setLevel(logging.INFO)
filehandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(filehandler)

class AlreadyDoneError(Exception):
    pass

def analyse_probecarddata(path, re, dump):
    if (not re) and os.path.isfile('%s/analyse_output.json'%path):
        raise AlreadyDoneError(path)

    logger.info("Analysing '%s' at the PID %d"%(path, os.getpid()))

    results = {}
    for Test in [PowerTest,BackbiasIV,DACScan,ADC,PowerOnReset,ChipID,SEU,Registers,FIFOTest,DataPort,DigitalScan,FakeHitRate,AnalogueScanDataPort,ThresholdScanDataPortQueue,AnalogueScanDataPort3V,DigitalScan3V]:
        logger.info("%s::%s"%(path, Test.__name__))
        test=Test()
        results[Test.__name__] = test.analyse(path+'/'+test.path())
        # print(results[Test.__name__])
    if dump:
        # save test results to file
        with open('%s/analyse_output.json'%path, 'w') as content_file:
            json.dump(results, content_file, sort_keys=True, indent=4)
    results.clear()

def wrapper(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except KeyboardInterrupt:
        return
    
def wrapped_analyse(job):
    path, reanalyse, no_dump = job
    return wrapper(analyse_probecarddata, path, reanalyse, not no_dump)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('PATH', type=str, nargs='+', help='Path of the data. Must be end with CERN_PC/YYYYMMDD-HHMMSS form.')
    parser.add_argument('--no_dump', action='store_true', help='Add the option if you not want to dump the results to "analyse_output.json".')
    parser.add_argument('--reanalyse', action='store_true', help='Do the analyse even if analyse_output.json exist')
    parser.add_argument('-j', '--jobs', type=int, default=1, help='Number of the jobs to use')
    args=parser.parse_args()

    if args.jobs > mp.cpu_count():
        logger.warning("Number of jobs (%d) is bigger than CPU count (%d)"%(args.jobs, mp.cpu_count()))
        logger.warning("Setting number of jobs to %d"%mp.cpu_count())
        args.jobs = mp.cpu_count()

    matched_paths = itertools.chain(
        *(glob.iglob(basepath) for basepath in args.PATH)
    )
    try:
        ipath = [
            str(require_testdata_path(path))
            for path in matched_paths
        ]
    except ValueError as exc:
        parser.error(str(exc))

    if not ipath:
        parser.error(
            "No matching test-run folders found under %s" % TESTDATA_ROOT
        )

    logger.info("############ Start analysing the data ############")
    p = mp.Pool(args.jobs)
    jobs = ((path, args.reanalyse, args.no_dump) for path in ipath)
    iresult = p.imap(wrapped_analyse, jobs)

    while True:
        try:
            next(iresult)
        except StopIteration:
            break
        except AlreadyDoneError as e:
            logger.warning("Analysing '%s' has already been done - ignore"%e.args[0])
        except IOError as e:
            logger.exception(e)
        except KeyboardInterrupt as e:
            logger.exception(e)
            break

    p.terminate()

    logger.info("############ Analysing has finished ############")
