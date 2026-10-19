import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

ROWS_AT_A_TIME=4
VHI=170
VLO=100
DVLO=0
DVHI=20
N_INJ=10

class AnalogueScan(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Analogue Scan','Measure if all pixels respond to analogue pulsing')

    def read_event(self,pc,chipid):
        pc.write_alpide_reg(chipid,0,0,1,0x0000) # config mode
        ev=[]
        for region in range(32):
            for addr in range(128):
                data_hi=pc.read_alpide_reg(chipid,region,2,addr)
                if data_hi==0xF3:
                    break
                data_lo=pc.read_alpide_reg(chipid,region,1,addr)
                word=(data_hi&0xFF)<<16|data_lo
                addr=word>>8&0x3FFF
                hitmap=word&0x7F
                ev.append(alpide.xy(region,addr))
                for bit in range(8):
                    if hitmap>>bit&0x1==0x1:
                        ev.append(alpide.xy(region,addr+1+bit))
                assert addr!=127
        return ev
        
    def run(self,pc,path):
        total=0
        chipid=17
        of=open('%s/events.txt'%path,'w')
        self.total_steps=1 #FIXME
        self.current_step=0
        pc.init_alpide(chipid)
        pc.write_alpide_reg(chipid,0,6,5,VHI) # VPULSEH
        pc.write_alpide_reg(chipid,0,6,6,VLO) # VPULSEL
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
        alpide.set_mask_all(pc,chipid,False)
        for y in range(0,512,ROWS_AT_A_TIME):
            logging.info('... rows %d-%d...'%(y,y+ROWS_AT_A_TIME-1))
            alpide_set_pulsing_all(pc,chipid,False)
            for yy in range(y,y+ROWS_AT_A_TIME):
                alpide_set_pulsing_row(pc,chipid,yy,True)
            for region in range(32):
                pc.write_alpide_reg(chipid,region,2,0,0xF3)
            pc.send_alpide_opcode(0x63)              # reset readout!
            pc.write_alpide_reg(chipid,0,0,1,0x0025) # Triggered read-out, 20 MHz, clustering
            pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
            pc.write_alpide_reg(chipid,0,0,5,    40) # FROMU Configuration Register 2: strobe length
            pc.write_alpide_reg(chipid,0,0,6,     0) # FROMU Pulsing Register 1: delay strobe-pulse
            pc.write_alpide_reg(chipid,0,0,7,  2000) # FROMU Pulsing Register 2: pulse duration
            pc.send_alpide_opcode(0x78)              # pulse!
            ev=self.read_event(pc,chipid)
            of.write('# EVENT ROWS=%d-%d\n'%(y,y+ROWS_AT_A_TIME+1))
            for xy in ev:
                 of.write('%4d %3d\n'%xy)
            total+=len(ev)
        of.close()
        logging.info("Total %d pixel responses"%(total))
        return True

    def analyse(self,path):
        f=open('%s/events.txt'%path)
        hitmap=np.zeros((512,1024))
        for line in f:
            if re.match('#',line):
                continue
            x,y=map(int,line.split())
            hitmap[y,x]+=1
        ndead=0
        nnoise=0
        for n in hitmap.flat:
            if n==0:
                ndead+=1
            if n>1:
                nnoise+=1
        plt.figure()
        #plt.title('Hitmap')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        #plt.xticks([0.5,64.5,127.5,190.5,254.5],['0','64','127','190','254'])
        #plt.yticks([0.5,64.5,128.5,192.5,255.5],['0','64','128','192','255'])
        plt.pcolor(hitmap)
        plt.savefig('%s/hitmap.png'%path)
        plt.close()
        return {'ndead':ndead,'nnoise':nnoise}


