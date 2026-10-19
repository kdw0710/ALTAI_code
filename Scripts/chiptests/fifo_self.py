import logging
from probecard import alpide
import time
from chiptests import Test

class FIFOSelfTest(Test):
    def __init__(self):
        super(self.__class__,self).__init__('FIFO self test test','Test if the FIFO self test works')

    def run(self,pc,path):
        of=open('%s/result.txt'%path,'w')
        chipid=17
        alpide.init(pc,chipid)
        pc.write_alpide_reg(chipid,0,0,0xFF01) # start FIFO self test
        time.sleep(0.001)
        for reg_addr in range(32):
            status=pc.read_alpide_reg(chipid,reg_addr,3,1)
            lo=pc.read_alpide_reg(chipid,reg_addr,1,127)
            hi=pc.read_alpide_reg(chipid,reg_addr,2,127)
            data=hi<<8|lo
            if status!=0 or data!=0xAAAAAA:
                of.write('region %d: status=%04X, data=%06X\n',reg_addr,status,data)
        of.close()
        return True

    def analyse(self,path):
        pass

