import logging
from probecard import alpide
from chiptests import AnalogueScanDataPort

VHI=170
VLO=100

class AnalogueScanDataPort3V(AnalogueScanDataPort):
    def __init__(self,name='Analogue Scan DP 3V',descr='Measure if all pixels respond to analogue pulsing at VBB=-3V'):
        super(AnalogueScanDataPort3V,self).__init__(name=name,descr=descr)

    def init(self,pc,chipid):
        alpide.init(pc,chipid,bb=True,vbb=-3)
        pc.write_alpide_reg(chipid,0,6,5,VHI) # VPULSEH
        pc.write_alpide_reg(chipid,0,6,6,VLO) # VPULSEL
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
        pc.write_alpide_reg(chipid,0,6,4,105) # VCASN (for VBB=-3V) 
        pc.write_alpide_reg(chipid,0,6,7,117) # VCASN2 (for VBB=-3V)
        pc.write_alpide_reg(chipid,0,6,8, 60) # VCLIP (for VBB=-3V) 
        alpide.set_mask_all(pc,chipid,False)
        #        pc.write_alpide_reg(chipid,0,0,1,0x0021) # Triggered read-out, 20 MHz, clustering: 0x21 -> disabled, 0x25 -> enabled
        #        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        #        pc.write_alpide_reg(chipid,0,0,5,    40) # FROMU Configuration Register 2: strobe length
        #        pc.write_alpide_reg(chipid,0,0,6,     0) # FROMU Pulsing Register 1: delay strobe-pulse
        #        pc.write_alpide_reg(chipid,0,0,7,  2000) # FROMU Pulsing Register 2: pulse duration
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, 20 MHz, clustering: 0x1F9 -> disabled, 0x1FD -> enabled
        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,   200) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: delay strobe-pulse
        pc.write_alpide_reg(chipid,0,0,8,  2000) # FROMU Pulsing Register 2: pulse duration
        alpide.reset_readout(pc)
        pc.send_alpide_opcode(0xE4) # Pixel matrix reset
        
    def run(self,pc,path):
        #try:
        chipid=17
        self.init(pc,chipid)
        return super(AnalogueScanDataPort3V,self).pulse_looop(pc,chipid,path)
        #except:
        #    logging.exception('Test aborted by exception')
        #    return True # V3 is not a required test
