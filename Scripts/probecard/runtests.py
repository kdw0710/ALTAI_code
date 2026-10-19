#!/usr/bin/env python3

#import palpide3patch

import time
try:
    from . import probecard
except ImportError:
    import probecard
import os, sys
import logging
from datetime import datetime
import subprocess
from chiptests import *

logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')
#logging.basicConfig(level=logging.DEBUG,format='%(asctime)s - %(levelname)s - %(message)s')

def runtests(pc,prefix):
    global_result=True

    test_time=datetime.now()
    test_folder=test_time.strftime('%Y%m%d-%H%M%S') # identical to ALICIA format
    test_path = '%s/%s'%(prefix,test_folder)
    os.makedirs(test_path)
    # write git diff to file
    script_path=os.path.dirname(os.path.realpath(sys.argv[0])) 
    og=open('%s/git_diff.txt'%test_path,'w')
    current_branch=subprocess.run(
        ['git', 'symbolic-ref', '--short', 'HEAD'],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    og.write(subprocess.run(
        ['git', 'log', '-n', '1', 'origin..%s'%current_branch],
        check=False,
        capture_output=True,
        text=True,
    ).stdout)
    og.write(subprocess.run(
        ['git', 'diff', 'origin..%s'%current_branch],
        check=False,
        capture_output=True,
        text=True,
    ).stdout)
    og.close()
 
    # file and stderr
    logHandler=logging.FileHandler(test_path + '/test.log')
    logging.getLogger().addHandler(logHandler)
    logging.info('On ALPIDE-mass-testing-software branch: %s'%(current_branch))

    fpga_dna=pc.read_fpga_dna()
    logging.info('FPGA DNA: 0x%015X'%fpga_dna)
    firmware_date_lo=pc.read_pc_reg(probecard.PC_STS_BUS,19)
    firmware_date_hi=pc.read_pc_reg(probecard.PC_STS_BUS,20)
    firmware_hash_lo=pc.read_pc_reg(probecard.PC_STS_BUS, 0)
    firmware_hash_hi=pc.read_pc_reg(probecard.PC_STS_BUS, 1)
    firmware_year ='20%02X'%(firmware_date_hi>>8&0xFF)
    firmware_month='%02X'%(firmware_date_hi>>0&0xFF)
    firmware_day  ='%02X'%(firmware_date_lo>>8&0xFF)
    firmware_hour ='%02X'%(firmware_date_lo>>0&0xFF)
    firmware_hash =firmware_hash_hi<<16|firmware_hash_lo
    logging.info('Probecard firmware: %08X, dated %s-%s-%s %s:00'%(firmware_hash,firmware_year,firmware_month,firmware_day,firmware_hour))

    # timestamps
    fTS=open("%s/timestamps.txt"%test_path,'a')

    try:
        # (original list) for Test in [PowerTest,BackbiasIV,DACScan,ADC,PowerOnReset,ChipID,SEU,Registers,FIFOTest,DataPort,DigitalScan,FakeHitRate,AnalogueScanDataPort,ThresholdScanDataPortQueue,HSLink,AnalogueScanDataPort3V,DigitalScan3V]:
        for Test in [PowerTest,DACScan,ADC,PowerOnReset,ChipID,SEU,Registers,FIFOTest,DataPort,DigitalScan,FakeHitRate,AnalogueScanDataPort,ThresholdScanDataPortQueue,HSLink]:
            test=Test()
            fTS.write('%s : BEGIN %s\n'%(datetime.now().strftime('%s'),test.name))
            path='%s/%s/'%(test_path,test.path())
            logging.info('Running Test "%s" (results go to "%s")...'%(test.name,path))
            if os.path.exists(path):
                raise Exception('Error: directory %s exists already...'%path)
            os.makedirs(path)
            result=test.run(pc,path)
            #result=test.run(path,Backbias = False)
            #time.sleep(0.1)
            #result=test.run(path, Backbias = True)
            fTS.write('%s : END %s\n'%(datetime.now().strftime('%s'),test.name))
            pc.enable_parallel_port(False)
            pc.enable_serial_port(False)
            n=pc.purge_parallel_port()
            if n>0:
                logging.warning('Parallel port not empty afer "%s" (%d bytes remaining).'%(test.name,n))
                result=False
            n=pc.purge_serial_port()
            if n>0:
                logging.warning('Serial port not empty afer "%s" (%d bytes remaining).'%(test.name,n))
                result=False
            n=pc.purge_ctrl_port()
            if n>0:
                logging.warning('Control port not empty afer "%s" (%d bytes remaining).'%(test.name,n))
                result=False

            status=pc.power_status()
            if status[0]!=1:
                logging.warning('During test "%s" the power supply tripped',test.name)
                if status[1]==1:
                    logging.warning(' -> analogue supply tripped')
                if status[2]==1:
                    logging.warning(' -> digital supply tripped')
                if status[3]==1:
                    logging.warning(' -> pwell supply tripped')
                if status[4]==1:
                    logging.warning(' -> sub supply tripped')
            
            if result==True:
                logging.info('Test "%s" successful: results in "%s".'%(test.name,path))
            else:
                logging.warning('Test "%s" FAILED: results in "%s".'%(test.name,path))
                global_result=False
                if test.abort_on_failure():
                    logging.warning('Further tests are omitted.')
                    break
    except:
        logging.exception('Test aborted by exception')
        #status=pc.power_status()
        #if status[0]!=1:
        #    logging.warning('The power supply tripped')
        #    if status[1]==1:
        #        logging.warning(' -> analogue supply tripped')
        #    if status[2]==1:
        #        logging.warning(' -> digital supply tripped')
        #    if status[3]==1:
        #        logging.warning(' -> pwell supply tripped')
        #    if status[4]==1:
        #        logging.warning(' -> sub supply tripped')
        #else:
        #    logging.info('Power OK')
        pc.power_off()
        logging.info('Purging ports...')
        pc.enable_parallel_port(False)
        pc.enable_serial_port(False)
        n=pc.purge_parallel_port()
        logging.warning('- parallel port: %d bytes left.'%n)
        n=pc.purge_serial_port()
        logging.warning('- serial port: %d bytes left.'%n)
        n=pc.purge_ctrl_port()
        logging.warning('- control port port: %d bytes left.'%n)
        # check contacts once more
        time.sleep(0.5)
        c=pc.test_contacts()
        good,tot=sum(c),len(c)
        logging.info('  -> %d/%d pads in contact'%(good,tot))
        for pad,status in zip(probecard.ALPIDE_PADS,c):
            if not status:
                logging.info('   ... %s missing'%str(pad))
        # TODO print the pads which are not contacted
        global_result=False
    
    fTS.close()
    pc.power_off()

    logging.getLogger().removeHandler(logHandler)
    
    # indicate test finished without exception
    open(test_path+'/tests_completed', 'w')
    return global_result
