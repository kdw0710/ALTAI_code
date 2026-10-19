#!/usr/bin/env python3

import sys
import os
import glob
import pickle
import json
import traceback
import subprocess

sys.path.append('../')
from chiptests import *
from classification import *

import numpy as np
import matplotlib.pyplot as plt


def get_chip_from_path(path):
    if 'TR00' in path: # path pattern of probestation with tray
      chip_id=path[path.find('CERN_PC')-11:path.find('CERN_PC')-1]
      return chip_id
    else: # path pattern of probestation with wafer
      chip_id=path[path.find('CERN_PC')-14:path.find('CERN_PC')-1]
      return chip_id




def classify_probecarddata(basepath,processing_option,lot_id):
    check_list=[]
    path_list=[]
    results_list=[]
    test_names=[]
    path_list_tmp=[]
    listChips = {}
    f_paths=open('%s/%s_paths_yieldsum.txt'%(basepath,lot_id),'w')

    ### for use with path /home/alice/transferred/
    if processing_option==0:
        searchPath = basepath
    elif processing_option==3:
        searchPath = '{:s}/*/*/Chips/*/*/CERN_PC/*/'.format(basepath)
        print('Scanning through probecard test data for {:d} folders.'.format(len(glob.glob(searchPath))))
    else:
        searchPath = '{:s}/*/*/Chips/*/*/CERN_PC/*/'.format(basepath)
        print('Scanning through probecard test data for {:d} folders.'.format(len(glob.glob(searchPath))))

    for path in glob.iglob(searchPath):
        if 'BOTT' in path: # very old identification of trays, before giving them ids -> skip
            continue
        properties = path.split('/')
        ind = properties.index('CERN_PC')
        if properties[ind-3] != 'Chips':
          raise ValueError('Path structure not as expected: {:s}!'.format(path))

        chip_id = properties[ind-1]
        timestamp = properties[ind+1]
#        if not ('T700789' in chip_id or 'T700087' in  chip_id):
#        if not ('T700789' in chip_id):
        if not (lot_id in chip_id):
          try:
            with open("{:s}/../../chip_id.txt".format(path), 'r') as content_file:
              chip_id=content_file.read()
#              if not ('T700789' in chip_id or 'T700087' in  chip_id):
#              if not ('T700789' in chip_id):
              if not (lot_id in chip_id):
                  continue
          except IOError:
            continue

        # Add timestamp + path to the list for this reticle
        if not chip_id in listChips.keys():
          listChips[chip_id] = []
        listChips[chip_id].append([timestamp, path])

#    print listChips

    class_glb_AB=0
    class_glb_Bad=0
    chip_count_per_die=[0 for i in range(0,46)]
    short_yield_per_die=[0 for i in range(0,46)]
    power_yield_per_die=[0 for i in range(0,46)]
    functional_yield_per_die=[0 for i in range(0,46)]

    for chip_id, chip_data in listChips.items():
        die=int(chip_id[-6:-4]) #CKT
        #die=int(chip_id[-2:])
        print(chip_id, die)
        chip_sorted=sorted(chip_data,key=lambda elem: elem[0],reverse=True)
        for testrun in chip_sorted:
            path=testrun[1]
            if processing_option!=0:
                print(path)


            path_list_tmp.append([chip_id,path])

            try:
                analysis_results = json.load(open('%s/analyse_output.json'%path, "r"))
            except IOError:
                #print('Cannot find analyse_output.json in {:s}'.format(path))
                try:
                    analysis_results = pickle.load(open('%s/analyse_output.p'%path, "rb"))
                except IOError:
                    print('Cannot find analyse_output.p in {:s}'.format(path))
                    continue

#
##            subprocess.check_output(['scp', '%s/analyse*'%path, 'aliceits@alpide.cern.ch:%s'%path.replace('/home/palpidefs/probestation/transferred/','/eos/project/a/alice-its/PROBESTATION-1/')])
#            myfiles='%sanalyse*'%path
#            destination='aliceits@alpide.cern.ch:%s'%path.replace('/home/palpidefs/probestation/transferred/','/eos/project/a/alice-its/PROBESTATION-1/')
#            #subprocess.check_output(['scp', myfiles, destination])
#            os.system('scp %s %s'%(myfiles,destination))

            try:
                classification_results = json.load(open('%s/classification.json'%path, "r"))
            except IOError:
                #print('Cannot find classification.json in {:s}'.format(path))
                try:
                    classification_results = pickle.load(open('%s/classification.p'%path, "rb"))
                except IOError:
                    print('Cannot find classification.p in {:s}'.format(path))
                    continue
            except ValueError:
                print('Cannot open classification.p in {:s}'.format(path))
                continue

            classification_version=classification_results['version']
            if int(classification_version)<3:
                #print 'too old version: ', classification_version
                continue

            tests = [PowerTest,BackbiasIV,PowerOnReset,ChipID,FIFOTest,DACScan,DataPort,AnalogueScanDataPort,ThresholdScanDataPortQueue]
#            tests = [PowerTest,BackbiasIV,PowerOnReset,ChipID,FIFOTest,DACScan,DataPort,AnalogueScanDataPort,ThresholdScanDataPort]
            for Test in tests:
                   try:
                    test=Test()
                    print("\t\tShortTest: %s"%('CategoryAB' if analysis_results[Test.__name__]['failure']!=True else 'Bad'))
                    print("\t\t%s: %s"%(Test.__name__,classification_results[Test.__name__]['global']))

                    if Test.__name__=='PowerTest':
                        short_yield_per_die[die]+=(1 if analysis_results[Test.__name__]['failure']!=True else 0)
                        power_yield_per_die[die]+=(1 if classification_results[Test.__name__]['global']!='Bad' else 0)
                        chip_count_per_die[die]+=1
                        functional_yield_per_die[die]+=(1 if classification_results['global']!='Bad' else 0)
                        class_glb_AB+=(1 if classification_results['global']!='Bad' else 0)                        
                        break

                   except KeyError:
                    print('\t\tWARNING: key {:s} not found in results file, will be classified as {:s}.'.format(Test.__name__, CLASSIFICATION_BAD))
                    classification_results[Test.__name__]={'global': CLASSIFICATION_BAD}
                    print("\t\t%s: %s"%(Test.__name__,CLASSIFICATION_BAD))

                   except Exception as e:
                    print(e)
                    traceback.print_exc()
                  

            print("\tGlobal: %s"%classification_results['global'])

            break

    for p in sorted(path_list_tmp):
      f_paths.write('%s\t%s\n'%(p[0],p[1]))



    print('probable number of wafers: ', max(chip_count_per_die))
    print('sample: ', sum(chip_count_per_die))
    print('avg powering yield: ', sum(power_yield_per_die)/float(sum(chip_count_per_die)))
    print('avg short yield: ', sum(short_yield_per_die)/float(sum(chip_count_per_die)))
    print('avg functional yield: ', sum(functional_yield_per_die)/float(sum(chip_count_per_die)))
    print('####')
    print('avg fnctl yield: ', float(class_glb_AB)/sum(chip_count_per_die))
    print('####')

    f_functional=open('%s/%s_functional_yield_per_die.txt'%(basepath,lot_id), 'w')
    f_short=open('%s/%s_short_yield_per_die.txt'%(basepath,lot_id), 'w')
    f_power=open('%s/%s_power_yield_per_die.txt'%(basepath,lot_id), 'w')

    for die in range(0,46):
        functional_yield_per_die[die]/=(float(chip_count_per_die[die]) if chip_count_per_die[die]!=0 else 1)
        f_functional.write('%d\t%d\t%0.3f\n'%(die,chip_count_per_die[die],functional_yield_per_die[die]))
        short_yield_per_die[die]/=(float(chip_count_per_die[die]) if chip_count_per_die[die]!=0 else 1)
        f_short.write('%d\t%d\t%0.3f\n'%(die,chip_count_per_die[die],short_yield_per_die[die]))
        power_yield_per_die[die]/=(float(chip_count_per_die[die]) if chip_count_per_die[die]!=0 else 1)
        f_power.write('%d\t%d\t%0.3f\n'%(die,chip_count_per_die[die],power_yield_per_die[die]))


if len(sys.argv) > 1:
    base_path=sys.argv[1]
    processing_option=0
    # 0 -> latest test; 2 -> all measurements;
    # 1 -> the latest measurements of each chip;
    # 2 -> all measurements;
    # 3 -> latest measurements of each chip on a wafer or tray
    lot_id=None
    if len(sys.argv) == 3:
        processing_option=int(sys.argv[2])
    elif len(sys.argv) > 3:
        processing_option=int(sys.argv[2])
        if processing_option!=3:
            print('If you want to process tray of wafer put processing option==3')
            sys.exit()
        lot_id=sys.argv[3]

    classify_probecarddata(base_path,processing_option,lot_id)

