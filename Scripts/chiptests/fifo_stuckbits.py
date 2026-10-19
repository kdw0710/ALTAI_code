import logging
import re
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

        lines=resultsFile.split('\n')
        bit_list=[]
        for l in lines:
            #print l
            if 'Error in region' in l:
                ldata=l.split() 
                region=int(ldata[3].replace(',',''),0)
                address=int(ldata[5].replace(':',''),0)
                val_written=int(ldata[10],0)
                val_read=int(ldata[7],0)
                #print region, address, val_written, val_read
                #print bin(val_read^val_written)
                for bit, bitval in enumerate(bin(val_read^val_written)[::-1]):
                    if bitval=='1':
                        bit_list.append([region, address, bit])

        bits_stuck = [list(item) for item in set(tuple(bit) for bit in bit_list)] 

        if len(bits_stuck)>resultsFile.count('Error in region'):
            print('Assumingly issue in address encoder, trying to find it..')
            bit_list=[]
            current_pattern_name=''
            current_pattern=[]
            written_addr=0
            for l in lines:
                if 'reading pattern' in l:
                    #current_pattern_name=l.split()[4].replace('"','').replace(')','')
                    current_pattern_name=re.search(r'(reading pattern "(.*?)")',l).group(2)
                    for name,pattern in PATTERNS:
                        if name==current_pattern_name:
                            current_pattern=pattern 
                            print('###', current_pattern_name)

                if 'Error in region' in l:
                    ldata=l.split() 
                    region=int(ldata[3].replace(',',''),0)
                    address=int(ldata[5].replace(':',''),0)
                    val_written=int(ldata[10],0)
                    val_read=int(ldata[7],0)

                    bits_tmp=[]
                    if current_pattern_name!='checker board' and current_pattern_name!='marching': # non-repeating patterns..
                        for addr in range(128):
                            data=current_pattern[region*128+addr]
                            if data==val_read:
                                written_addr=addr 
                                bits_tmp.append([written_addr, [pos for pos, char in enumerate(bin(address^written_addr)[::-1]) if char == '1']])

                    else: # more than one good match possible due to repeating patterns..
                        for addr in range(address, 128):
                            data=current_pattern[region*128+addr]
                            if data==val_read:
                                written_addr=addr 
                                bits_tmp.append([written_addr, [pos for pos, char in enumerate(bin(address^written_addr)[::-1]) if char == '1']])
                                break

                    min_len=128
                    diffbit=[] 
                    #print bits_tmp
                    for b in bits_tmp:
                        if len(b[1])<min_len:
                            min_len=len(b[1])
                            diffbit=b[1][0]
                            written_addr=b[0]

                    bit_list.append([region, diffbit])

            #print bit_list
            #address_bits_stuck = [bit for bit in set([bit[0] for bit in bit_list])]
            print(set(tuple(bit) for bit in bit_list))
            address_bits_stuck = [list(item) for item in set(tuple(bit) for bit in bit_list)] 
            return {'fifo_region_errors': resultsFile.count('Error in region'),
                    'n_bits_stuck': 0,
                    'bits_stuck': [],
                    'n_address_bits_stuck': len(address_bits_stuck),
                    'address_bits_stuck': address_bits_stuck
                    }

        else:
            return {'fifo_region_errors': resultsFile.count('Error in region'),
                    'n_bits_stuck': len(bits_stuck),
                    'bits_stuck': bits_stuck,
                    'n_address_bits_stuck': 0,
                    'address_bits_stuck': []
                    }


        # TODO cover case of stuck address bits and stuck memory bit





