import logging
import re
from probecard import alpide
import time
from probecard import probecard
from chiptests import Test

class DataPortTiming(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Data port timing','Tests all bits of the data port by forcing values and scans the data port timing')

    # test timing
    def run(self,pc,path):
        
          # to restore later
        original_phase = pc.read_pc_reg(probecard.PC_DATA_BUS,0) # parallel bus sampling phase
        original_delay0  = pc.read_pc_reg(probecard.PC_DATA_BUS,26) & 0x1F
        original_delay1  = pc.read_pc_reg(probecard.PC_DATA_BUS,26) >> 5
        original_delay2  = pc.read_pc_reg(probecard.PC_DATA_BUS,27) & 0x1F
        original_delay3  = pc.read_pc_reg(probecard.PC_DATA_BUS,27) >> 5
        
        chipid=17
        of=open('%s/events.txt'%path,'w')
        of.write("# SET\tREAD\tOK\tBITWISE_XOR\n")
        alpide.init(pc,chipid)
        pc.enable_parallel_port()
        error=False
        for phase in [0, 1, 2, 3]:
                pc.write_pc_reg(probecard.PC_DATA_BUS, 0, phase)
                for databit in range(4):
                    logging.info('Scanning phase %d and databit %d'%(phase, databit))
                    of.write('# SCAN BIT=%d\n'%databit) # parallel bus sampling phase
                    for delay in range(32):

                        delay_data0 = original_delay0
                        delay_data1 = original_delay1
                        delay_data2 = original_delay2
                        delay_data3 = original_delay3
                        
                        if databit==0:
                            delay_data0 = delay
                        if databit==1:
                            delay_data1 = delay
                        if databit==2:
                            delay_data2 = delay
                        if databit==3:
                            delay_data3 = delay

                        pc.write_pc_reg(probecard.PC_DATA_BUS, 24, delay_data1 << 5 | delay_data0)
                        pc.write_pc_reg(probecard.PC_DATA_BUS, 25, delay_data3 << 5 | delay_data2)

                        of.write('# SAMPLE PHASE=%d\n'%pc.read_pc_reg(probecard.PC_DATA_BUS,0)) # parallel bus sampling phase
                        of.write('# DELAYS=%d %d %d %d\n'%(pc.read_pc_reg(probecard.PC_DATA_BUS,26) & 0x1F,pc.read_pc_reg(probecard.PC_DATA_BUS,26) >> 5,pc.read_pc_reg(probecard.PC_DATA_BUS,27) & 0x1F,pc.read_pc_reg(probecard.PC_DATA_BUS,27) >> 5))

                        no_errors = 0
                        for w in range(255): # NB: no FF
                            pc.write_alpide_reg_queue(chipid,0,7,1,w<<1|0x1)
                            pc.write_alpide_reg_queue(chipid,0,7,1,0)
                            pc.flush_alpide_queue()
                            time.sleep(0.001)
                            data=pc.read_pc_reg(probecard.PC_DATA_BUS,1) >> 8
                            if data!=w:
                                #logging.warn('... set data port to 0x%02X but read 0x%02X (%s)'%(w,data,bin(w^data)))
                                error=True
                                no_errors+=1
                            of.write('0x%02X\t0x%02X\t%d\t%s\n'%(w,data,data==w,bin(w^data)))
                        of.write('# Errors=%d\n\n'%no_errors)
        of.close()
        pc.power_off()
        
        # restore old values
        pc.write_pc_reg(probecard.PC_DATA_BUS, 0,  original_phase)
        pc.write_pc_reg(probecard.PC_DATA_BUS, 24, original_delay1 << 5 | original_delay1)
        pc.write_pc_reg(probecard.PC_DATA_BUS, 25, original_delay3 << 5 | original_delay2)
        
        return True # not error

    def analyse(self,path):
        try:
            of=open('%s/events.txt'%path)
        except IOError:
            print('ERROR: File {:s}/events.txt could not be read!'.format(path))
            return {}
 
        errors=0
        for line in of:
            if line.startswith('#') or len(line) < 2:
                continue
            set,read,status,bitwisecomparison=line.split()
            if int(status)!=1:
                errors+=1
       
        of.close()
      
        return { 'data_port_timing_errors': errors}
