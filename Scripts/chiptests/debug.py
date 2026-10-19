import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

NITERATIONS=10

class Debug(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Debug','Playground for debugging')

    def run(self,pc,path):
        total=0
        chipid=0
        alpide.init(pc,chipid)
        of=open('%s/events.dat'%path,'w')
        pc.write_alpide_reg(chipid,0,0,4,0x0040) # FROMU Configuration Register 1: disable busy monitoring, digital test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,   200) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: pulse-strobe delay
        pc.write_alpide_reg(chipid,0,0,8,  20) # FROMU Pulsing Register 2: pulse length
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, clustering: FD, no clustering F9

        pc.purge_serial

        of.close()
        return True

