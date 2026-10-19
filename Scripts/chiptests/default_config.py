import logging
from probecard import alpide
import time
from chiptests import Test

class DefaultConfig(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Default config test','Test the automatic configration')

    def run(self,pc,path):
        alpide.init(pc,chipid=16)
        of=open('%s/result.txt'%path,'w')
        # OB master
        logging.info('   - OB master')
        for modid in range(1,8): # 0 is IB
            for rowid in range(2):
                chipid=modid<<4|rowid<<3
                alpide.init(pc,chipid)
                print(modid,rowid,chipid)
                pc.write_alpide_reg(chipid,0,0,0,0xFF02) # load default cfg (unfortunately enables manchester...)
                cfg=pc.read_alpide_reg(chipid,0,0,0x10)
                if cfg&0x0010!=0x0010 and cfg&0x000F!=(chipid&0x000F)+6:
                    logging.warn('OB master with chipid=%02X has wrong cfg: %04X'%(chipid,cfg))
                    of.write('%02X\t%02X (bad)\n'%(chipid,cfg))
                    nerr+=1
                else:
                    of.write('%02X\t%02X (ok)\n'%(chipid,cfg))
        # OB slave
        logging.info('   - OB slave')
        nerr=0
        for modid in range(1,8): # 0 is IB
            for rowid in range(2):
                for geoid in range(1,7): # 0 is master, 7 is broadcast
                    chipid=modid<<4|rowid<<3|geoid
                    alpide.init(pc,chipid)
                    pc.write_alpide_reg(chipid,0,0,0,0xFF02) # load defualt cfg 
                    cfg=pc.read_alpide_reg(chipid,0,0,0x10)
                    if cfg&0x0010!=0 and cfg&0x000F!=(chipid&0x000F)-1:
                        logging.warn('OB slave with chipid=%02X has wrong cfg: %04X'%(chipid,cfg))
                        of.write('%02X\t%02X (bad)\n'%(chipid,cfg))
                        nerr+=1
                    else:
                        of.write('%02X\t%02X (ok)\n'%(chipid,cfg))
        of.close()
        if nerr==0:
            logging.info('... all OK')
        else:
            logging.warn('... total %d errors found'%nerr)
        return True

    def analyse(self,path):
        pass

