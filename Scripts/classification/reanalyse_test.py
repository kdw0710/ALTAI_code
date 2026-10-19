#!/usr/bin/env python3

import sys
import os
import glob
import pickle
import json
import traceback
import configparser as ConfigParser
import subprocess

sys.path.append('../database')
from database_production import DB
sys.path.append('../classification')
from classification import *
sys.path.append('../chiptests')
from chiptests import *

def parse_test_log(path):
    pass








def reanalyse(basepath,processing_option,tray_id):
    #DB
    #script_path=os.path.dirname(os.path.realpath(__file__))
    #config=ConfigParser.ConfigParser()
    #config.read(script_path + '/../config/setup.cfg')
    #location=config.get('DB','location')

    #database_config=ConfigParser.ConfigParser()
    #database_config.read(script_path + '/../config/database_production.cfg')
    #try:
    #  #TODO add location from general config
    #  db=DB(database_config,location)
    #except Exception as e:
    #  print e
    #  print(traceback.format_exc())
    #  print '\nDatabase connection FAILED.'
    #  sys.exit()

    path_list=[]
    check_list=[]
    listChips = {}

    if processing_option==0:
        searchPath = basepath
    elif processing_option==3:
        searchPath = '{:s}/*/*/Chips/{:s}/*/CERN_PC/*/'.format(basepath,tray_id) 
        print('Scanning through probecard test data for {:d} folders.'.format(len(glob.glob(searchPath))))
    else:
        searchPath = '{:s}/*/*/Chips/*/*/CERN_PC/*/'.format(basepath) 
        print('Scanning through probecard test data for {:d} folders.'.format(len(glob.glob(searchPath))))

    for path in glob.iglob(searchPath):
        if 'BOTT' in path: # very old identification of trays, before giving them ids -> skip
            continue
#        if int(path[-16:-8])<20170405:  # from on 20170404 lunchtime only ThrehsoldScanDataPort is replaced by ThresholdScanDataPortQueue
#            continue
        properties = path.split('/')
        ind = properties.index('CERN_PC')
        if properties[ind-3] != 'Chips':
          raise ValueError('Path structure not as expected: {:s}!'.format(path))

        #chip_id = properties[ind-1]
        chip_id=''
        timestamp = properties[ind+1]
        try:
          with open("{:s}/../../chip_id.txt".format(path), 'r') as content_file:
            chip_id=content_file.read()
        except IOError:
          continue

        # Add timestamp + path to the list for this reticle
        if not chip_id in listChips.keys():
          listChips[chip_id] = []
        listChips[chip_id].append([timestamp, path])

    for chip_id, chip_data in listChips.items():
        chip_sorted=sorted(chip_data,key=lambda elem: elem[0],reverse=True)
        for testrun in chip_sorted:
            path=testrun[1]
            if processing_option!=0:
                print(path)

            try:
                ana = json.load(open('%s/analyse_output.json'%path, "r"))
            except IOError:
                print('Cannot find analyse_output.json in {:s}'.format(path))
                try:
                    ana = pickle.load(open('%s/analyse_output.p'%path, "rb"))
                except IOError:
                    print('Cannot find analyse_output.p in {:s}'.format(path))
                    continue
            except ValueError:
                print('Cannot open analyse_output.p in {:s}'.format(path))
                continue
            #print ana

            ana_cpy=ana

            ana_new = {}
            print('reanalyzing probecard test data for chip.')
            for Test in [ADC]:
                test=Test()
                ana_new[Test.__name__] = test.analyse(path+'/'+test.path())
                #print(ana_new[Test.__name__])
            
                ana_cpy[Test.__name__] = ana_new[Test.__name__]
          
            #print ana_cpy

            if True:
                # save test results to file
                with open('%s/reanalyse_output.json'%path, 'w') as content_file:
                  json.dump(ana_cpy, content_file, sort_keys=True, indent=4)







            #try:
            #    classification_results = json.load(open('%s/classification.json'%path, "r"))
            #except IOError:
            #    print('Cannot find classification.json in {:s}'.format(path))
            #    try:
            #        classification_results = pickle.load(open('%s/classification.p'%path, "r"))
            #    except IOError:
            #        print('Cannot find classification.p in {:s}'.format(path))
            #        continue
            #except ValueError:
            #    print('Cannot open classification.p in {:s}'.format(path))
            #    continue

            print('--> chip ID: %s'%chip_id)

            ## check classification version of classification.p file
            #classification_version=classification_results['version']
            #print('\t--> Current classification version of classification.json(.p) file: %s'%classification_version)

            ## check classification version in repository
            #repo_classification_version = CLASSIFICATION['version']
            #print('\t--> Current classification version in repository: %s'%repo_classification_version)
      
            ##db.get_component_activityhistory(chip_id)
            #db_classification_version=str(db.get_component_lastclassification_version(chip_id))
            #print('\t--> Version of classification last stored in database: %s'%db_classification_version)

            #if repo_classification_version!=db_classification_version:
            ##if True:
            #    # TODO: do not redo this unnecessarily..
            #    print('\t----> Classification not up to date, redoing it with version %s'%repo_classification_version)
            #    classification_information = subprocess.check_output(["%s/../classify.py"%script_path, '%s'%(path)])
            #    print classification_information
            #    classification_version = classification_information.split()[classification_information.split().index('Version:')+1]
            #    f=open("%s/classify.txt"%(path),'a')
            #    f.write(classification_information)
            #    f.close()

            #    # retrieve chip functional status
            #    #classEntry = pickle.load( open( "%s/classification.p"%(path), "r" ) )
            #    try:
            #        classEntry = json.load(open('%s/classification.json'%path, "r"))
            #    except IOError:
            #        print('Cannot find classification.json in {:s}'.format(path))
            #        try:
            #            classEntry = pickle.load(open('%s/classification.p'%path, "r"))
            #        except IOError:
            #            print('Cannot find classification.p in {:s}'.format(path))
            #            continue
            #    if classEntry['global'] == 'CategoryA':
            #        functional_status='OK'
            #    elif classEntry['global'] == 'CategoryB':
            #        functional_status='OR'
            #    else:
            #        functional_status='NK'

            #    print '  --> Functional status (from this classification): ', functional_status
            #    physical_status=db.get_component_physicalstatus(chip_id)
            #    print '  --> Physical status (from data base): ', physical_status
  
            #    # define classification
            #    classification='NK'
            #    if functional_status=='OK' and physical_status=='OK':
            #        classification='OK'
            #    elif functional_status=='OR' and physical_status=='OK':
            #        classification='OR'
            #    elif functional_status=='NK' and physical_status=='OK':
            #        classification='NK'
            #    elif physical_status=='Damaged':
            #        classification='DM'
            #    else:
            #        print 'WARNING: classification result not defined, omitting further action!\n'
            #        #return 
            #
            #    print '-> Classification results will be updated in data base to: %s\n'%database_config.get("Classifications", classification)

            #    db.save_classification_result(chip_id,classification,classification_information,classification_version)         
            #    #return

            #else:
            #    print '-> Classification up to date, omitting further action\n'
            #    #return

            break


if len(sys.argv) > 1:
    base_path=sys.argv[1]
    processing_option=1 
    # 0 -> latest test; 
    # 1 -> the latest measurements of each chip
    # 2 -> all measurements; 
    # 3 -> latest measurements of chips in tray or wafer
    tray_id=None
    if len(sys.argv) == 3:
        processing_option=int(sys.argv[2])
    elif len(sys.argv) > 3:
        processing_option=int(sys.argv[2])
        if processing_option!=3:
            print('If you want to process tray of wafer put processing option==3')
            sys.exit()
        tray_id=sys.argv[3]

    reanalyse(base_path,processing_option,tray_id)

