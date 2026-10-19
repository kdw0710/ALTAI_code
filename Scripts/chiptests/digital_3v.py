from probecard import alpide
from chiptests import DigitalScan
import logging

class DigitalScan3V(DigitalScan):
    def __init__(self,name='Digital Scan 3V',descr='Measure if all pixels respond to digital pulsing at VBB=-3V'):
        super(DigitalScan3V,self).__init__(name=name,descr=descr)

    def init(self,pc,chipid):
        alpide.init(pc,chipid,bb=True,vbb=-3)
        pc.write_alpide_reg(chipid,0,6,4,0x0000) # VCASN=0
        pc.write_alpide_reg(chipid,0,6,13,0x0000) # IBIAS=0
        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,   200) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: pulse-strobe delay
        pc.write_alpide_reg(chipid,0,0,8,  20) # FROMU Pulsing Register 2: pulse length
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, clustering: FD, no clustering F9
    def run(self,pc,path):
        #try:
        chipid=17
        self.init(pc,chipid)
        return super(DigitalScan3V,self).run_test(pc,chipid,path)
        #except:
        #    logging.exception('Test aborted by exception')
        #    return True # V3 is not a required test
