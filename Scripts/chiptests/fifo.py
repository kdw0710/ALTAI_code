import logging
from probecard import alpide
from chiptests import Test

PATTERNS=[
  ('ramp'         ,range(128*32)                          ),
  ('zeros'        ,[0]*(128*32)                           ),
  ('ones'         ,[0xFFFFFF]*(128*32)                    ),
  ('marching'     ,[1<<i for i in range(24)]*171         ),
  ('checker board',[0xAAAAAA,0x555555]*(64*32)            ),
  ('prime'        ,[(i*17)&0xFFFFFF for i in range(128*32)])
]

class FIFOTest(Test):
    def __init__(self):
        super(self.__class__,self).__init__('FIFO Test','Test of all region memories')

    def run(self,pc,path):
        of=open('%s/result.txt'%path,'w')
        chipid=17
        self.total_steps=32*128*len(PATTERNS)*2
        self.current_step=0
        alpide.init(pc,chipid)
        for name,pattern in PATTERNS:
            logging.info('... pattern "%s"...'%name)
            of.write('Step %d/%d... (writing pattern "%s")\n'%(self.current_step,self.total_steps,name))
            for region in range(32):
                for addr in range(128):
                    data=pattern[region*128+addr]
                    pc.write_alpide_reg_queue(chipid,region,1,addr,data>> 0&0xFFFF)
                    pc.write_alpide_reg_queue(chipid,region,2,addr,data>>16&0x00FF)
                    self.current_step+=1
            pc.flush_alpide_queue()
            of.write('Step %d/%d... (reading pattern "%s")\n'%(self.current_step,self.total_steps,name))
            nerr=0
            for region in range(32):
                for addr in range(128):
                    pc.read_alpide_reg_queue(chipid,region,2,addr) # data_hi
                    pc.read_alpide_reg_queue(chipid,region,1,addr) # data_lo
                ret=pc.flush_alpide_queue(chipid)
                for addr in range(128):
                    data_hi=ret.pop(0)
                    data_lo=ret.pop(0)
                    data=(data_hi&0xFF)<<16|data_lo
                    if data!=pattern[region*128+addr]:
                        nerr+=1
                        of.write('Error in region %d, address 0x%02X: read 0x%06X instead of 0x%06X\n'%(region,addr,data,pattern[region*128+addr]))
                    self.current_step+=1
            if nerr==0:
                logging.info('   -> OK')
                of.write('OK: no read back errors\n')
            else:
                logging.warning('   -> %d errors'%nerr)
        of.close()
        return nerr==0

    def analyse(self,path):
        try:
            resultsFile = open('%s/result.txt'%path).read()
        except IOError:
            print('ERROR: File {:s}/result.txt could not be read!'.format(path))
            return {}

        return {'fifo_region_errors': resultsFile.count('Error in region')}

