import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

class MaskRegion(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Mask region','Test if mask all regions work')

    def run(self,pc,path):
        total=17
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

        pc.send_alpide_opcode(0x63)   # rdo reset!

        alpide.set_mask_all(chipid,False)
        alpide.set_pulsing_all(chipid,True)

        # only enable region 0
        pc.write_alpide_reg(chipid,0,0,2,0xFFFE)
        pc.write_alpide_reg(chipid,0,0,3,0xFFFF)

        # disable all columns on region 0
        pc.write_alpide_reg(chipid,0,3,0,0xFFFF)

        evs=[]

        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))

        pc.write_alpide_reg(chipid,0,0,2,0xFFFF)
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))

        # enable all regions
        pc.write_alpide_reg(chipid,0,0,2,0)
        pc.write_alpide_reg(chipid,0,0,3,0)
        # disable all double columns
        for reg_addr in range(32):
            pc.write_alpide_reg(chipid,reg_addr,3,0,0xFFFF)
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(self.read_event(pc,chipid))

        for i,ev in enumerate(evs):
            of.write('# EVENT %d\n'%i)
            for xy in ev:
                 of.write('%4d %3d\n'%xy)

        of.close()
        return True

    def analyse(self,path):
        f=open('%s/events.txt'%path)


