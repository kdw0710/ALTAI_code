import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

class PanicMode(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Panic mode','Test if panic mode')

    def run(self,pc,path):
        chipid=16
        alpide.init(pc,chipid)
        pc.write_alpide_reg(chipid,0,6,4,0x0000) # VCASN=0
        pc.purge_parallel_port()
        pc.enable_parallel_port()
        of=open('%s/events.txt'%path,'w')
        pc.write_alpide_reg(chipid,0,0,1,0x00FD) # Triggered read-out, clustering
        pc.write_alpide_reg(chipid,0,0,5,     7) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     1) # FROMU Pulsing Register 2: pulse delay
        pc.write_alpide_reg(chipid,0,0,8,    10) # FROMU Pulsing Register 2: pulse length

        alpide.set_mask_all(pc,chipid,True)
        alpide.set_pulsing_all(pc,chipid,False)

        evs=[]
        #pc.write_alpide_reg(chipid,0,0,0,0xFF10) # Xoff!
        pc.send_alpide_opcode(0x78)   # pulse!
        evs.append(pc.read_parallel_port()[0])
        for _ in range(56):
            pc.send_alpide_opcode(0x55)   # trigger!
            evs.append(pc.read_parallel_port()[0])
        pc.write_alpide_reg(chipid,0,0,0,0xFF11) # Xon!

        for i,ev in enumerate(evs):
            of.write('# EVENT %d\n'%i)
            print(ev)
            for b in ev:
                 of.write('%02X\n'%b)

        of.close()
        return True

    def analyse(self,path):
        f=open('%s/events.txt'%path)
        # expected stuff (modulo time stamps)
        # 1st event: a0 57 c0 00 00 7f 00 08 7f bc
        # 2nd-rest: a0 58 bc
        # expect all events


