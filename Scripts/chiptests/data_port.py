import logging
import re
from probecard import alpide
import time
from probecard import probecard
from chiptests import Test

class DataPort(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Data port','Tests all bits of the data port by forcing values')

    def run(self,pc,path):
        chipid=17
        of=open('%s/events.txt'%path,'w')
        of.write("# SET\tREAD\tOK\tBITWISE_XOR\n")
        alpide.init(pc,chipid)
        pc.enable_parallel_port()
        error=False
        for w in range(255)*4: # NB: no FF
            pc.write_alpide_reg_queue(chipid,0,7,1,w<<1|0x1)
            pc.write_alpide_reg_queue(chipid,0,7,1,0)
            pc.flush_alpide_queue()
            time.sleep(0.001)
            data=pc.read_pc_reg(probecard.PC_DATA_BUS,1) >> 8
            if data!=w:
                logging.warn('... set data port to 0x%02X but read 0x%02X (%s)'%(w,data,bin(w^data)))
                error=True
            of.write('0x%02X\t0x%02X\t%d\t%s\n'%(w,data,data==w,bin(w^data)))
        of.close()
        pc.enable_parallel_port(False)
        pc.purge_parallel_port()
        return not error

    def analyse(self,path):
        try:
            of=open('%s/events.txt'%path)
        except IOError:
            print('ERROR: File {:s}/events.txt could not be read!'.format(path))
            return {}
 
        errors=0
        for line in of:
            if line.startswith('#'):
                continue
            set,read,status,bitwisecomparison=line.split()
            if int(status)!=1:
                errors+=1
       
        of.close()
      
        return { 'data_port_errors': errors}
