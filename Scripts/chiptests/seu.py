import logging
from probecard import alpide
from chiptests import Test

class SEU(Test):
    def __init__(self):
        super(self.__class__,self).__init__('SEU','Reads the SEU counters')

    def run(self,pc,path):
        chipid=17
        of=open('%s/seus.txt'%path,'w')
        alpide.init(pc,chipid)
        # TMR!
        pc.read_alpide_reg_queue(chipid,0,7,0)
        pc.read_alpide_reg_queue(chipid,0,7,0)
        pc.read_alpide_reg_queue(chipid,0,7,0)
        nseu1,nseu2,nseu3=pc.flush_alpide_queue(chipid)
        of.write('# Number of SEUs (1st read): %d\n'%nseu1) 
        of.write('# Number of SEUs (2nd read): %d\n'%nseu2) 
        of.write('# Number of SEUs (3rd read): %d\n'%nseu3) 
        nseu=nseu1+nseu2+nseu3
        if nseu>0:
            logging.warning('... SEU counters reads reported %d, %d, and %d SEUs'%(nseu1,nseu2,nseu3))

        pc.send_alpide_opcode(0xAA) # DEBUG
        for _ in range(2):
            pc.read_alpide_reg_queue(chipid,0,7,2)
        for _ in range(4):
            pc.read_alpide_reg_queue(chipid,0,7,3)
        for _ in range(5):
            pc.read_alpide_reg_queue(chipid,0,7,4)
        for _ in range(65):
            pc.read_alpide_reg_queue(chipid,0,7,5)
        for _ in range(9):
            pc.read_alpide_reg_queue(chipid,0,7,6)
        for _ in range(4):
            pc.read_alpide_reg_queue(chipid,0,7,7)
        words=pc.flush_alpide_queue(chipid)
        seu_bmu  = words[               1]>>11&0x1==0x1
        seu_dmu  = words[         2    +3]>>10&0x1==0x1
        seu_tmu  = words[       4+2    +4]>>10&0x1==0x1
        seu_rru  =[words[     5+4+2+2*i+2]>>15&0x1==0x1 for i in reversed(range(32))]
        seu_fromu= words[  65+5+4+2    +1]>>12&0x1==0x1
        seu_adc  = words[9+65+5+4+2    +3]>>14&0x1==0x1
        if seu_bmu:
            logging.warning('... SEU detected in BMU')
        if seu_dmu:
            logging.warning('... SEU detected in DMU')
        if seu_tmu:
            logging.warning('... SEU detected in TMU')
        for region,seu in enumerate(seu_rru):
            if seu:
                logging.warning('... SEU detected in RRU, region %d'%region)
        if seu_fromu:
            logging.warning('... SEU detected in FROMU')
        if seu_adc:
            logging.warning('... SEU detected in ADC')
        of.write('# DEBUG chain:\n')
        of.write(' '.join(map(lambda w:'%04X'%w,words))+'\n') 

        # TODO: for now we better continue
        #if nseu>0 or any([seu_bmu,seu_dmu,seu_tmu,any(seu_rru),seu_fromu,seu_adc]):
        #    return False
        #else:
        #    return True
        return True


    def analyse(self,path):
        try:
          f=open('%s/seus.txt'%path,'r')
        except IOError:
            print('ERROR: File {:s}/seus.txt could not be read!'.format(path))
            return {}
        lines=f.readlines()
        if len(lines)==0:
            return {}
        n1=int(lines[0].split()[-1])
        n2=int(lines[1].split()[-1])
        n3=int(lines[2].split()[-1])
        dbg = [int(x,16) for x in lines[4].split()]
        seu_bmu  = dbg[               1]>>11&0x1==0x1
        seu_dmu  = dbg[         2    +3]>>10&0x1==0x1
        seu_tmu  = dbg[       4+2    +4]>>10&0x1==0x1
        seu_rru  =[dbg[     5+4+2+2*i+2]>>15&0x1==0x1 for i in reversed(range(32))]
        seu_fromu= dbg[  65+5+4+2    +1]>>12&0x1==0x1
        seu_adc  = dbg[9+65+5+4+2    +3]>>14&0x1==0x1
        return {'seus':max(n1,n2,n3),'seu-bmu:':seu_bmu,'seu-dmu':seu_dmu,'seu-tmu':seu_tmu,'seu-fromu':seu_fromu,'seu-adc':seu_adc,'seu-rru':seu_rru}


