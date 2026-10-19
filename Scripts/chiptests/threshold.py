import logging
import re
import numpy as np
import matplotlib.pyplot as plt
from chiptests import Test

ROWS_AT_A_TIME=4
VHI=170
DVLO=0
DVHI=20
N_INJ=10

class ThresholdScan(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Threshold Scan','Measure s-curves for pixles')

    def xy(self,region,addr):
        d=region<<14|addr
        x=d>>9&0x3FE|(d^d>>1)&0x1
        y=d>>1&0x1FF
        return (x,y)
 
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
                ev.append(self.xy(region,addr))
                for bit in range(8):
                    if hitmap>>bit&0x1==0x1:
                        ev.append(self.xy(region,addr+1+bit))
                assert addr!=127
        return ev

    def mask_all(self,pc,chipid,mask=True):
        pc.write_alpide_reg(chipid,0,5,0,(1 if mask else 0)<<11|1<<10|1<<9) # Pixel CFG reg 1: write MASK, all rows
        pc.write_alpide_reg(chipid,0,5,1,1<<10)            # Pixel CFG reg 2: all columns
        pc.write_alpide_reg(chipid,0,5,2,1)                # Pixel CFG reg 3: strobe on
        pc.write_alpide_reg(chipid,0,5,2,0)                # Pixel CFG reg 3: strobe off

    def pulsing_all(self,pc,chipid,enable=True):
        pc.write_alpide_reg(chipid,0,5,1,1<<10)            # Pixel CFG reg 2: all columns
        pc.write_alpide_reg(chipid,0,5,0,(1 if enable else 0)<<11|0<<10|1<<9) # Pixel CFG reg 1: write PULSE, all rows
        pc.write_alpide_reg(chipid,0,5,2,1)                # Pixel CFG reg 3: strobe on
        pc.write_alpide_reg(chipid,0,5,2,0)                # Pixel CFG reg 3: strobe off

    def pulsing_xy(self,pc,chipid,x,y,enable=True):
        raise #FIXME

    def pulsing_row(self,pc,chipid,y,enable=True):
        pc.write_alpide_reg(chipid,0,5,0,(1 if enable else 0)<<11|0<<10|0<<9|y)    # Pixel CFG reg 1: write PULSE, row y
        pc.write_alpide_reg(chipid,0,5,1,1<<10)            # Pixel CFG reg 2: all columns
        pc.write_alpide_reg(chipid,0,5,2,1)                # Pixel CFG reg 3: strobe on
        pc.write_alpide_reg(chipid,0,5,2,0)                # Pixel CFG reg 3: strobe off
        
    def run(self,pc,path):
        chipid=0 #FIXME
        of=open('%s/events.txt'%path,'w')
        self.total_steps=1 #FIXME
        self.current_step=0
        pc.init_alpide(chipid)
        pc.write_alpide_reg(chipid,0,6,5,VHI) # VPULSEH
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
        self.mask_all(pc,chipid,False)
        #for y in range(0,512,ROWS_AT_A_TIME):
        for y in [250]:
            logging.info('... rows %d-%d...'%(y,y+ROWS_AT_A_TIME-1))
            self.pulsing_all(pc,chipid,False)
            for yy in range(y,y+ROWS_AT_A_TIME):
                self.pulsing_row(pc,chipid,yy,True)
            for dv in range(DVLO,DVHI+1):
                logging.info('   ... charge %d...'%dv)
                pc.write_alpide_reg(chipid,0,6,6,VHI-dv) # VPULSEL
                for i in range(N_INJ):
                   # logging.info('      ... injection %d/%d...'%(i,N_INJ))
                    #for region in range(32):
                    #    pc.write_alpide_reg(chipid,region,2,0,0xF3)
                    pc.send_alpide_opcode(0x63)              # reset readout!
                    pc.write_alpide_reg(chipid,0,0,1,0x0025) # Triggered read-out, 20 MHz, clustering
                    pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
                    pc.write_alpide_reg(chipid,0,0,5,    40) # FROMU Configuration Register 2: strobe length
                    pc.write_alpide_reg(chipid,0,0,6,     0) # FROMU Pulsing Register 1: delay strobe-pulse
                    pc.write_alpide_reg(chipid,0,0,7,  2000) # FROMU Pulsing Register 2: pulse duration
                    pc.send_alpide_opcode(0x78)              # pulse!
                    ev=self.read_event(pc,chipid)
                    of.write('# EVENT ROWS=%d-%d DV=%d\n'%(y,y+ROWS_AT_A_TIME+1,dv))
                    for xy in ev:
                         of.write('%4d %3d\n'%xy)
        of.close()
        return True

    def scurve_fit(self,steps,x,y):
        dvs=sorted(steps.keys())
        #print "\t".join(map(str,[steps[dv][1][y*1024+x] for dv in dvs]))
        m=0
        s=0
        den=0
        for dv1,dv2 in zip(dvs[:-1],dvs[1:]):
            ddv=dv2-dv1
            mdv=0.5*(dv2+dv1)
            n1=1.0*steps[dv1][1][y*1024+x]/steps[dv1][0]
            n2=1.0*steps[dv2][1][y*1024+x]/steps[dv2][0]
            dn=n2-n1
            den+=dn/ddv
            m+=mdv*dn/ddv 
            s+=mdv**2*dn/ddv 
        if den>0:
            if s>0:
                s=(s-m*m)**0.5
            m/=den
            s/=den
        return m,s 

    def analyse(self,path):
        f=open('%s/events.txt'%path)
        steps={}
        reline=re.compile('EVENT')
        redv  =re.compile(r'DV=(\d+)')
        for line in f:
            if re.search(reline,line):
                dv=int(re.search(redv,line).group(1))
                if not dv in steps:
                    steps[dv]=[1,[0]*(1<<19)]
                else:
                    steps[dv][0]+=1
            else:
               x,y=map(int,line.split())
               steps[dv][1][y*1024+x]+=1

        thrshs=[]
        sth=0
        sthth=0
        thrmap=np.zeros((512,1024))
        for x in range(1024):
            for y in range(512):
                m,s=self.scurve_fit(steps,x,y)
                sth  +=m
                sthth+=m*m
                print(x,y,m,s)
                thrmap[y,x]=m
                thrshs.append(m)
        #plt.figure()
        #plt.xlabel('Threshold in DAC')
        #plt.ylabel('Frequency')
        #plt.title('Whole ALPIDE')
        #plt.hist(thrshs,range(20))
        #plt.savefig('%s/whole.png'%path)
        #plt.close()

        plt.figure()
        plt.title('Threshold map')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        plt.pcolor(thrmap)
        plt.savefig('%s/thrmap.png'%path)
        plt.close()

