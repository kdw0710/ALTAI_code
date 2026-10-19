import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

class RotationScan(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Rotation test','Test automatic pulse rotation')

    def run(self,pc,path):
        chipid=17
        alpide.init(pc,chipid)
        pc.write_chip_reg(chipid,0,6,4,0x0000) # VCASN=0
        pc.enable_parallel_port()
        of=open('%s/events.txt'%path,'w')
        pc.write_alpide_reg(chipid,0,0,5,     7) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     1) # FROMU Pulsing Register 2: pulse delay
        pc.write_alpide_reg(chipid,0,0,8,    10) # FROMU Pulsing Register 2: pulse length

        alpide.set_pulsing_all(pc,chipid,False)
        alpide.set_pulsing_row(pc,chipid,0)
        alpide.set_pulsing_row(pc,chipid,3)
        alpide.set_mask_all(pc,chipid,True)
        alpide.set_mask_row(pc,chipid,0,False)
        alpide.set_mask_row(pc,chipid,3,False)

        pc.write_chip_reg(chipid,0,4,0x88,1)
        pc.write_alpide_reg(chipid,0,0,1,0x00FD) # Triggered read-out, clustering
        for i in range(16):
             pc.send_alpide_opcode(0x78)   # pulse!
             ev=self.read_event(pc,chipid)
             of.write('# EVENT %d\n'%(i))
             for xy in ev:
                  of.write('%4d %3d\n'%xy)
        pc.write_alpide_reg(chipid,0,0,1,0x00F9) # Triggered read-out, no clustering
        for i in range(16):
             pc.send_alpide_opcode(0x78)   # pulse!
             ev=self.read_event(pc,chipid)
             of.write('# EVENT %d\n'%(i))
             for xy in ev:
                  of.write('%4d %3d\n'%xy)
        of.close()
        return True

    def analyse(self,path):
        f=open('%s/events.txt'%path)


