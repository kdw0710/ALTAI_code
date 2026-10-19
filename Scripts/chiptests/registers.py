import logging
from probecard import alpide
from chiptests import Test

# TODO: with and w/o clock gating

class Registers(Test):
    #TODO reg 0, E, F, 10
    GLOBAL_REGISTERS=[
      (0,0,0x01,0x03FF),
      (0,0,0x02,0xFFFF),
      (0,0,0x03,0xFFFF),
      (0,0,0x04,0x07FF),
      (0,0,0x05,0xFFFF),
      (0,0,0x06,0xFFFF),
      (0,0,0x07,0xFFFF),
      (0,0,0x08,0xFFFF),
      (0,0,0x14,0x01FF),
      (0,0,0x15,0x0FFF),
      (0,0,0x17,0xFFFF),
      (0,0,0x18,0x7FFF),
      (0,0,0x19,0xFFFF),
      (0,0,0x1A,0x03FF),
      (0,0,0x1B,0x001F),
      (0,5,0x00,0x0003),
      (0,6,0x00,0x07FF),
      (0,6,0x01,0x00FF),
      (0,6,0x02,0x00FF),
      (0,6,0x03,0x00FF),
      (0,6,0x04,0x00FF),
      (0,6,0x05,0x00FF),
      (0,6,0x06,0x00FF),
      (0,6,0x07,0x00FF),
      (0,6,0x08,0x00FF),
      (0,6,0x09,0x00FF),
      (0,6,0x0A,0x00FF),
      (0,6,0x0B,0x00FF),
      (0,6,0x0C,0x00FF),
      (0,6,0x0D,0x00FF),
      (0,6,0x0E,0x00FF),
      (0,6,0x0F,0x00FF),
      (0,6,0x10,0x0FFF),
      (0,6,0x11,0x07FF),
    ]
    REGION_REGISTERS=[
      (0,3,0x0,0xFFFF),
      (0,4,0x1,0xFFFF),
      (0,4,0x2,0xFFFF),
      (0,4,0x4,0xFFFF),
      (0,4,0x8,0xFFFF),
    ]
    PATTERNS=[0x5555,0xAAAA,0x0000,0xFFFF,0xDEAD,0xF001,0xBEAF]

    def __init__(self):
        super(self.__class__,self).__init__('Register test','Write and read all R/W register bits`')

    def run(self,pc,path):
        of=open('%s/result.txt'%path,'w')
        chipid=17
        alpide.init(pc,chipid)

        nerr=0
        for rgn_addr,base_addr,sub_addr,mask in self.GLOBAL_REGISTERS:
            for pattern in self.PATTERNS:
                pc.write_alpide_reg_queue(chipid,rgn_addr,base_addr,sub_addr,pattern&mask)
                pc.read_alpide_reg_queue(chipid,rgn_addr,base_addr,sub_addr)
        ret=pc.flush_alpide_queue(chipid)
        for rgn_addr,base_addr,sub_addr,mask in self.GLOBAL_REGISTERS:
            for pattern in self.PATTERNS:
                read=ret.pop(0)
                if read&mask!=pattern&mask:
                    of.write('(rgn_addr=%02X,base_addr=%02X,sub_addr=%02X) wrote %04X but read %04X'%(rgn_addr,base_addr,sub_addr,read&mask,pattern&mask))
                    nerr+=1

        for rgn_addr,base_addr,sub_addr,mask in self.REGION_REGISTERS:
            for pattern in self.PATTERNS:
                for rgn_addr in range(32):
                    pc.write_alpide_reg_queue(chipid,rgn_addr,base_addr,sub_addr,pattern&mask)
                    pc.read_alpide_reg_queue(chipid,rgn_addr,base_addr,sub_addr)
            ret=pc.flush_alpide_queue(chipid)
            for pattern in self.PATTERNS:
                for rgn_addr in range(32):
                    read=ret.pop(0)
                    if read&mask!=pattern&mask:
                        of.write('(rgn_addr=%02X,base_addr=%02X,sub_addr=%02X) wrote %04X but read %04X'%(rgn_addr,base_addr,sub_addr,read&mask,pattern&mask))
                        nerr+=1
        if nerr==0:
            logging.info('   -> OK')
            of.write('OK: no read back errors\n')
        else:
            logging.warning('   -> %d errors'%nerr)
        
        return nerr==0

    def analyse(self,path):
        try:
          f=open('%s/result.txt'%path,'r')
        except IOError:
            print('ERROR: File {:s}/result.txt could not be read!'.format(path))
            return {}
        errors=0 
        for line in f:
             if 'OK: no read back errors' not in line:
                  errors+=1
        return {'errors':errors}

