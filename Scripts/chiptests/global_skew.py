import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

class GlobalSekw(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Global skew','Test if global skewing is working')

    def run(self,pc,path):
        total=0
        chipid=16
        alpide.init(pc,chipid)
        pc.write_chip_reg(chipid,0,6,4,0x0000) # VCASN=0
        pc.enable_parallel_port()
        of=open('%s/events.txt'%path,'w')
        evs=[]
        for x in [0x013E,0x01BE,0x017E]: # no skew, rdo start skew, global skew
            pc.write_alpide_reg(chipid,0,0,1,x)
            pc.write_alpide_reg(chipid,0,0,4,0x0058)
            pc.write_alpide_reg(chipid,0,0,5,    10) # FROMU Configuration Register 2: strobe length
            pc.write_alpide_reg(chipid,0,0,6,     2)
            pc.write_alpide_reg(chipid,0,0,7,     1) # FROMU Pulsing Register 2: pulse delay
            pc.write_alpide_reg(chipid,0,0,8,    50) # FROMU Pulsing Register 2: pulse length

            alpide.set_mask_all(chipid,True)
            alpide.set_pulsing_all(chipid,False)

            for row in range(1,24,3):
                alpide.set_mask_xy(chipid,0,row,False)
                alpide.set_pulsing_xy(chipid,0,row,True)
                 
            pc.send_alpide_opcode(0x78)   # pulse!
            pc.write_alpide_reg(chipid,0,0,4,0x0050) # should come fast

            evs.append(self.read_event(pc,chipid)) # should look at first 4 events

        for i,ev in enumerate(evs):
            of.write('# EVENT %d\n'%i)
            for xy in ev:
                 of.write('%4d %3d\n'%xy)

        of.close()
        return True

    def analyse(self,path):
        f=open('%s/events.txt'%path)
        # expected results (ignore timestamps):
        # A) no skewing
        #   1)   a0 96 c0 00 03 10 00 0f 10 b5 
        #   2-4) a0 97 b4
        # B) rdo start skewing
        #   1)   a0 96 c0 00 03 10 b5 
        #   2-4) a0 97 b4
        # C) global skewing (same as (B))
        #   1)   a0 96 c0 00 03 10 b5 
        #   2-4) a0 97 b4


