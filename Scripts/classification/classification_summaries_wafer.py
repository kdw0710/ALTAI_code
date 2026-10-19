#!/usr/bin/env python3

import sys
import glob
import pickle
import json
import traceback

sys.path.append('../')
from chiptests import *
from classification import *

import numpy as np
import matplotlib.pyplot as plt


def get_chip_from_path(path):
    if 'TR00' in path: # path pattern of probestation with tray
      chip_id=path[path.find('CERN_PC')-11:path.find('CERN_PC')-1]
      return chip_id
      #chip_pos=chip_id[-2:]
      #tray_id=chip_id[:-2]
      #return chip_id, chip_pos, tray_id
    else: # path pattern of probestation with wafer
      chip_id=path[path.find('CERN_PC')-14:path.find('CERN_PC')-1]
      return chip_id
      #chip_pos=str(int(chip_id[-2:]))
      #wafer_id=chip_id[:-3]
      ##print chip_id, chip_pos, wafer_id
      #return chip_id, chip_pos, wafer_id

def create_classification_overview_table(basepath, classification_results, tray_id=''):
    fname=basepath + '/classification_summary.txt'
    if tray_id!='':
        fname=basepath + '/'+tray_id+'_classification_summary.txt'
    results_file=open(fname, 'w')
    results_file.write('# CHIP_ID      PATH                                                                                           GLOBAL      '
      '  Key missing?  PowerTest     BackbiasIV   PowerOnReset FIFOTest     DACScan      DataPort     AnanlogueScanDataPort  ThresholdScanDataPort\n')
    results_file.write('# -----------  --------------------------------------------------------------------------------------------   ------------'
      '  ------------  ------------  -----------  -----------  -----------  -----------  -----------  ---------------------  ---------------------\n')

    for cr in classification_results:
        print(cr)
        results_file.write('%11s | %89s | %11s | %12s | %11s | %10s | %10s | %10s | %10s | %10s | %20s | %20s |\n'%(
           cr['Chip'],cr['Path'],cr['Global'],cr['MissingKeys'],cr['PowerTest'],cr['BackbiasIV'],cr['PowerOnReset'],cr['FIFOTest'],
#           cr['DACScan'],cr['DataPort'],cr['AnalogueScanDataPort'],cr['ThresholdScanDataPort']))
           cr['DACScan'],cr['DataPort'],cr['AnalogueScanDataPort'],cr['ThresholdScanDataPortQueue']))

    results_file.close()
    print('Summary table written to {:s}'.format(fname))


def create_classification_correlation_table(basepath, classification_results, test_names, tray_id=''):
    #
    # create results correlation matrix
    #
    #                          |       --Test Result--       |
    #                          |  Cat A  |  Cat B  |   Bad   |
    #     ---------------------|---------|---------|---------|--
    #                          |         |         |         |
    #                    Cat A |         |         |         |
    #                          |         |         |         |
    #                        --|---------|---------|---------|--
    #     ---Global---         |         |         |         |
    #         ---        Cat B |         |         |         |
    #     ---Result---         |         |         |         |
    #                        --|---------|---------|---------|--
    #                          |         |         |         |
    #                    Bad   |         |         |         |
    #                          |         |         |         |
    #     ---------------------|---------|---------|---------|--
    #
    #
    test_results=[CLASSIFICATION_CATEGORYA, CLASSIFICATION_CATEGORYB, CLASSIFICATION_BAD]
    n_chips=len(classification_results)
    res_matrix_summary={}
    ## power test results -> accessible by 'missing keys'
    #power_test_results=[0,0,0]
    #for cr in classification_results: # loop through all chips tested, fill results matrix
    #    if cr['MissingKeys']==True: # power test assumingly failed
    #        power_test_results[2]+=1./n_chips
    #    else:
    #        power_test_results[0]+=1./n_chips
    # other test results
    test_names_and_global=test_names[:]
    test_names_and_global.insert(0,'Global')
    for test in test_names_and_global: # loop through all tests
        # correlation of each of the test results with results of other single test
        for othertest in test_names_and_global:
            res_matrix={}
            for tr_test in test_results:
                for tr_othertest in test_results:
                    res_matrix[tr_test+'/'+tr_othertest]=0
            for cr in classification_results: # loop through all chips tested, fill results matrix
                res_matrix[cr[test]+'/'+cr[othertest]]+=1./n_chips
            res_matrix_summary[test+'/'+othertest]=res_matrix

    #print res_matrix_summary

    if True: # write results to file
        test_names_and_global=test_names[:]
        test_names_and_global.insert(0,'Global')
        for test in test_names_and_global:
            print(test)
            fname=basepath + '/classification_correlation_'+test+'.txt'
            if tray_id!='':
                fname=basepath + '/'+tray_id+'_classification_correlation_'+test+'.txt'
            results_file=open(fname, 'w')
            for othertest in test_names_and_global:
                #print '\t',othertest
                results_file.write('##################################################################\n')
                results_file.write('##################################################################\n')
                results_file.write('                         ||        %s                             \n'%(othertest))
                results_file.write('%21s    ||   Category A | Category B | Bad       \n'%(test))
                results_file.write('------------------------------------------------------------------\n')
                sum_test=0
                sum_othertest=[0,0,0]
                for tr_test in test_results:
                    sum_cat=0
                    for tr_cr in test_results:
                        sum_cat+=res_matrix_summary[test+'/'+othertest][tr_test+'/'+tr_cr]
                    sum_test+=sum_cat
                    results_file.write('%10s  |'%(tr_test))
                    results_file.write('%10f  ||'%(sum_cat))
                    for j, tr_cr in enumerate(test_results):
                        results_file.write('%13f'%(res_matrix_summary[test+'/'+othertest][tr_test+'/'+tr_cr]))
                        sum_othertest[j]+=res_matrix_summary[test+'/'+othertest][tr_test+'/'+tr_cr]

                    results_file.write('\n')
                results_file.write('------------------------------------------------------------------\n')
                # sums of columns
                results_file.write('Sums        |%10f  ||%13f%13f%13f\n'%(sum_test,sum_othertest[0],sum_othertest[1],sum_othertest[2]))



def create_classification_dropout_chart(basepath, classification_results, test_names, tray_id=''):
    test_names.remove('DataPort')


    fname=basepath + '/classification_dropout_chart.txt'
    if tray_id!='':
        fname=basepath + '/'+tray_id+'_classification_dropout_chart.txt'
    results_file=open(fname, 'w')
    test_results=[CLASSIFICATION_CATEGORYA, CLASSIFICATION_CATEGORYB, CLASSIFICATION_BAD]
    n_chips=len(classification_results)
    prev_results=[0,0,0]
    for test in test_names: # loop through all tests
        # correlation of each of the test results with results of other single test
        sum_results=[0,0,0]
        for cr in classification_results: # loop through all chips tested
            test_result=[]
            for itest in test_names:
                test_result.append(cr[itest])
                if itest==test:
                    break

            global_result=Classification.combine_classification(test_result)
            sum_results[test_results.index(global_result)]+=1

        results_file.write(test+'\n')
        print(test)

        for i, cat in enumerate(test_results):
            change_abs = sum_results[i] - prev_results[i]
            change_rel = float(sum_results[i]) / n_chips - float(prev_results[i]) / n_chips
            str = '\t%10s:   %4d (%s%4d)   %5.1f%% (%s%4.1f%%)'%(cat, sum_results[i], '+' if change_abs>=0 else '-', abs(change_abs), float(sum_results[i])/n_chips*100, '+' if change_rel>=0 else '-', abs(change_rel*100))
            print(str)
            results_file.write(str + '\n')
        prev_results = sum_results


def classify_probecarddata(basepath,processing_option,tray_id):
    check_list=[]
    path_list=[]
    results_list=[]
    test_names=[]
    listChips = {}

    ### for use with path directly containing the analysis_output.p file
    #print('Classifying probecard test data for {:d} chips.'.format(len(glob.glob(basepath))))
    #for path in glob.iglob(basepath):

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

        reticle = properties[ind-1]
        reticle = reticle.replace(tray_id, '')
        timestamp = properties[ind+1]
        if properties[ind-2] != tray_id:
          # could be single chip test -> try to open chip_id.txt file
          chip_id=""
          try:
            with open("{:s}/../../chip_id.txt".format(path), 'r') as content_file:
              chip_id=content_file.read()
              #print chip_id
              if not tray_id in chip_id:
                  #print 'not demanded wafer'
                  continue
              else:
                  reticle=chip_id.replace(tray_id, '')
          except IOError:
            #print('No chip id for %s'%path)
            continue

        # Add timestamp + path to the list for this reticle
        if not reticle in listChips.keys():
          listChips[reticle] = []
        listChips[reticle].append([timestamp, path])
        #print listChips
        # e.g. {'R22':[ ['meaststmp1', 'path1'], ['meaststmp2', 'path2']]}

    print(listChips)


    for die, chip_data in listChips.items():
        print(reticle, die)
        chip=tray_id+die
        print(chip)
        chip_sorted=sorted(chip_data,key=lambda elem: elem[0],reverse=True)
        for testrun in chip_sorted:
            path=testrun[1]
            if processing_option!=0:
                print(path)
            # load analysis results
            try:
                analysis_results = json.load(open('%s/analyse_output.json'%path, "r"))
            except IOError:
                print('Cannot find analyse_output.json in {:s}'.format(path))
                try:
                    analysis_results = pickle.load(open('%s/analyse_output.p'%path, "rb"))
                except IOError:
                    print('Cannot find analyse_output.p in {:s}'.format(path))
                    continue

            # load classification results
            try:
                classification_results = json.load(open('%s/classification.json'%path, "r"))
            except IOError:
                print('Cannot find classification.json in {:s}'.format(path))
                try:
                    classification_results = pickle.load(open('%s/classification.p'%path, "rb"))
                except IOError:
                    print('Can also not find classification.p in {:s}'.format(path))
                    continue

            print("\tVersion: %s"%CLASSIFICATION['version'])
#            classification_result={}
            global_results=[]
            missing_keys=False

            tests = [PowerTest,BackbiasIV,PowerOnReset,ChipID,FIFOTest,DACScan,DataPort,AnalogueScanDataPort,ThresholdScanDataPortQueue]
#            tests = [PowerTest,BackbiasIV,PowerOnReset,ChipID,FIFOTest,DACScan,DataPort,AnalogueScanDataPort,ThresholdScanDataPort]
            #tests = [BackbiasIV,PowerOnReset,FIFOTest,DACScan,DataPort,AnalogueScanDataPort,ThresholdScanDataPort]
            for Test in tests:
                   try:
                    test=Test()
                    #try:
                    #classification_result[Test.__name__] = test.classify(analysis_results[Test.__name__],CLASSIFICATION[Test.__name__])
                    global_results.append(classification_results[Test.__name__]['global'])
                    print("\t\t%s: %s"%(Test.__name__,classification_results[Test.__name__]['global']))

                   except KeyError:
                    print('\t\tWARNING: key {:s} not found in results file, will be classified as {:s}.'.format(Test.__name__, CLASSIFICATION_BAD))
                    global_results.append(CLASSIFICATION_BAD)
                    #classification_result[Test.__name__]={'global': CLASSIFICATION_BAD}
                    print("\t\t%s: %s"%(Test.__name__,CLASSIFICATION_BAD))
                    missing_keys=True

                   except Exception as e:
                    print(e)
                    traceback.print_exc()
                    global_results.append(CLASSIFICATION_BAD)
                  
#            classification_result['global']=Classification.combine_classification(global_results)
#            classification_result['version']=CLASSIFICATION['version']
            print("\tGlobal: %s"%classification_results['global'])

            test_names=[]
            results_entry={}
            results_entry['Chip']=chip
            results_entry['Path']=path[path.find('transferred')+11:]
            results_entry['Global']=classification_results['global']
            results_entry['MissingKeys']=missing_keys 
            for i, Test in enumerate(tests):
                test=Test()
                results_entry[Test.__name__]=global_results[i]
                test_names.append(Test.__name__)

            results_list.append(results_entry)
            #results_list.append([chip,path[path.find('transferred')+11:],classification_result['global'],missing_keys])
            #results_list[-1].extend(global_results)
            #print(classification_result)

            #for i, j in classification_result.items():
            #  print i, j
            #print classification_result
#            with open('%s/classification.json'%path, 'w') as content_file:
#              json.dump(classification_result, content_file, sort_keys=True, indent=4)
            #print classification_result
            break

    if processing_option==1:
#        create_classification_overview_table(basepath, results_list)
#        create_classification_correlation_table(basepath, results_list, test_names)
        create_classification_dropout_chart(basepath, results_list, test_names)
    if processing_option==3:
#        create_classification_overview_table(basepath, results_list, tray_id)
#        create_classification_correlation_table(basepath, results_list, test_names, tray_id)
        create_classification_dropout_chart(basepath, results_list, test_names, tray_id)






if len(sys.argv) > 1:
    base_path=sys.argv[1]
    processing_option=0
    # 0 -> latest test; 2 -> all measurements;
    # 1 -> the latest measurements of each chip;
    # 2 -> all measurements;
    # 3 -> latest measurements of each chip on a wafer or tray
    tray_id=None
    if len(sys.argv) == 3:
        processing_option=int(sys.argv[2])
    elif len(sys.argv) > 3:
        processing_option=int(sys.argv[2])
        if processing_option!=3:
            print('If you want to process tray of wafer put processing option==3')
            sys.exit()
        tray_id=sys.argv[3]

    classify_probecarddata(base_path,processing_option,tray_id)

