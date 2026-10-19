import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

class FatalMode(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Fatal mode','Test if fatal mode works')

    def run(self,pc,path):
        chipid=16 #FIXME
        alpide.init(pc,chipid)
        pc.write_chip_reg(chipid,0,6,4,0x0000) # VCASN=0
        pc.enable_parallel_port()
        of=open('%s/events.txt'%path,'w')
        alpide.set_mask_all(pc,chipid,False)
        pc.write_alpide_reg(chipid,0,0,1,0x00FD) # Triggered read-out, clustering
        pc.write_alpide_reg(chipid,0,0,5,     7) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     1) # FROMU Pulsing Register 2: pulse delay
        pc.write_alpide_reg(chipid,0,0,8,    10) # FROMU Pulsing Register 2: pulse length

        alpide.set_mask_all(chipid,False)
        alpide.set_pulsing_all(chipid,True)

        pc.write_alpide_reg(chipid,0,0,0,0xFF10) # Xoff!
        pc.send_alpide_opcode(0x78)   # pulse!
        for _ in range(64):
            pc.send_alpide_opcode(0x55)   # trigger!
        pc.write_alpide_reg(chipid,0,0,0,0xFF11) # Xon!

        evs=[]
        evs.append(self.read_event(pc,chipid))
        for i,ev in enumerate(evs):
            of.write('# EVENT %d\n'%i)
            for xy in ev:
                 of.write('%4d %3d\n'%xy)

        of.close()
        return True

    def analyse(self,path):
        f=open('%s/events.txt'%path)
        # expected stuff (modulo time stamps)
        # 1st event: a0 57 c0 00 00 7f 00 08 7f be
        # 2nd-rest: a0 58 be
        # expect only 63 events


