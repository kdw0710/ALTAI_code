import logging
from probecard import probecard
from probecard import alpide
import time
import os
from .test import Test

class HSLink(Test):
    def __init__(self):
        super(self.__class__,self).__init__('HS Link','Test of high-speed link')

    def run(self,pc,path):
        chipid=16
        alpide.init(pc,chipid)
        of=open('%s/data.dat'%path,'w')
        ef=open('%s/events.dat'%path,'wb')

        pc.write_alpide_reg(chipid,0,0,0x14,0x085) # clear PLL off signal bit
        pc.write_alpide_reg(chipid,0,0,0x14,0x185) # reset PLL
        pc.write_alpide_reg(chipid,0,0,0x14,0x085) # run PLL
        lock=pc.read_alpide_reg(chipid,0,0,0x16)
        if lock>>8&1!=1:
            logging.warning('ALPIDE PLL has not locked...')
        of.write('LOCK: %04X\n'%lock)
        pc.enable_serial_port()
        pc.purge_serial_port()
 
        # 1) fixed pattern
        d0=0x55
        d2=0xAA
        of.write('# D0\tD1\t%D2\terrcnt\tD0\'\tD1\'\tD2\'\n')
        for d1 in range(256):
            pc.write_alpide_reg_queue(chipid,0,0,0x19,d1<<8|d0)
            pc.write_alpide_reg_queue(chipid,0,0,0x1A,d2)
            pc.write_alpide_reg_queue(chipid,0,0,0x18,0x5)  # enable test mode 
            pc.write_alpide_reg_queue(chipid,0,0,0x18,0x0)  # disable test
            pc.flush_alpide_queue(chipid)
            raw=pc.read_serial_port()
            errcnt=pc.read_pc_reg(probecard.PC_HSDATA_BUS,7)
            if len(raw)>0:
                of.write('%02X\t%02X\t%02X\t%d\t%02X\t%02X\t%02X\n'%(d0,d1,d2,errcnt,raw[0],raw[1],raw[2]))
            else:
                of.write('%02X\t%02X\t%02X\t%d\tN/A\n'%(d0,d1,d2,errcnt))
        of.write('LOCK: %04X\n'%lock)
        # 2) empty events
        ef.write(('LOCK: %04X\n' % lock).encode('ascii'))
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, clustering: FD, no clustering F9
        # disable all double columns
        for region in range(32):
            pc.write_alpide_reg(chipid,region,3,0,0xFFFF)
        for i in range(100):
            alpide.trigger(pc)
            raw=pc.read_serial_port()
            errcnt=pc.read_pc_reg(probecard.PC_HSDATA_BUS,7)
            ef.write(('#Event %d (errcnt=%d, length=%d):\n' % (i, errcnt, len(raw))).encode('ascii'))
            ef.write(bytes(raw))
            ef.write(b'\n')
        ef.write(('LOCK: %04X\n' % lock).encode('ascii'))
        return True

    def analyse(self,path):
        f=open('%s/data.dat'%path,'r')
        for line in f:
            x=int(x,16)
            if pbrs7 is None:
                pbrs7=x # assume the first one is correct... TODO: be more clever.
            else:
                pbrs7=pbrs7_next(pbrs7)
                if x!=pbrs7:
                    err+=1



