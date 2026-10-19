import logging
import re
from probecard import alpide
from probecard import probecard
import time
from chiptests import Test

class ChipID(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Chip ID test','Makes control transactions with all chip IDs')

    def testchipid(self,pc,chipid,of):
        pc.set_chipid(chipid)
        time.sleep(0.001)
        #time.sleep(0.1)
        alpide.global_reset(pc)
        #time.sleep(0.1)
        pc.write_alpide_reg(chipid,0,0,16,0x0070|chipid&0xF)
        alpide.reset_readout(pc)
        #time.sleep(0.1)
        of.write('#Testing chip id %d\n'%chipid)
        for i in range(100):
            if (i % 2 == 0):
                pc.write_alpide_reg_queue(chipid,0,0,7,0x55AA) # FROMU Pulsing Register 1
                pc.write_alpide_reg_queue(chipid,0,0,8,0xFFFF) # FROMU Pulsing Register 2
                pc.read_alpide_reg_queue(chipid,0,0,7)
                pc.read_alpide_reg_queue(chipid,0,0,8)
            else:
                pc.write_alpide_reg_queue(chipid,0,0,8,0x55AA) # FROMU Pulsing Register 1
                pc.write_alpide_reg_queue(chipid,0,0,7,0xFFFF) # FROMU Pulsing Register 2
                pc.read_alpide_reg_queue(chipid,0,0,8)
                pc.read_alpide_reg_queue(chipid,0,0,7)

            try:
                ret=pc.flush_alpide_queue(chipid)
            except probecard.CtrlChipIDMissmatch as e:
                logging.info('       ... ERROR')
                pc.purge_ctrl_port() # needed because we queued two read transactions
                of.write('error for chipid %d in iteration %d: %s\n'%(chipid,i,e))
                return False
            ret55AA=ret.pop(0)
            retFFFF=ret.pop(0)
            if ret55AA!=0x55AA or retFFFF!=0xFFFF:
                logging.info('       ... ERROR')
                of.write('error for chipid %d in iteration %d: %04X %04X (should be: 55AA FFFF)\n'%(chipid,i,ret55AA,retFFFF))
                return False
        of.write('#Chip id %d OK\n'%chipid)
        return True

    def run(self,pc,path):
        alpide.init(pc,chipid=0)
        of=open('%s/results.txt'%path,'w')
        chipids={}
        # IB
        good=True
        logging.info('   - IBs')
        for chipid in range(0xF): # 0xF is broadcast
            chipids[chipid]=self.testchipid(pc,chipid,of)
            if not chipids[chipid]:
                good=False
        if good:
            logging.info('    ... OK')
        else:
            logging.info('    ... ERROR')

       # OB slave
        good=True
        logging.info('   - OB slaves')
        for modid in range(1,8): # 0 is IB
            for rowid in range(2):
                for geoid in range(1,7): # 0 is master, 7 is broadcast
                    chipid=modid<<4|rowid<<3|geoid
                    chipids[chipid]=self.testchipid(pc,chipid,of)
                    if not chipids[chipid]:
                        good=False
        if good:
            logging.info('    ... OK')
        else:
            logging.info('    ... ERROR')
        # OB master
        good=True
        logging.info('   - OB masters')
        for modid in range(1,8): # 0 is I
            for rowid in range(2):
                chipid=modid<<4|rowid<<3
                chipids[chipid]=self.testchipid(pc,chipid,of)
                if not chipids[chipid]:
                    good=False
        if good:
            logging.info('    ... OK')
        else:
            logging.info('    ... ERROR')
        of.close()
        return all(chipids.values())

    def analyse(self,path):
        try:
            f=open('%s/results.txt'%path)
        except IOError:
            print('ERROR: File {:s}/results.txt could not be read!'.format(path))
            return {}
        TOTALTESTS=113
        errors=tests=ok=0
        re_error=re.compile('error for chipid')
        re_test=re.compile(r'Testing chip id (\d+)')
        re_ok=re.compile(r'Chip id (\d+) OK')
        for line in f:
            if re.search(re_error,line):
              errors+=1
            if re.search(re_test,line):
              tests+=1
            if re.search(re_ok,line):
              ok+=1
        return {'chip_id_errors': TOTALTESTS-ok}
        
