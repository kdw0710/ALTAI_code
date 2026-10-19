import logging
import re
import numpy as np
import time
import matplotlib.pyplot as plt
from probecard import alpide
from chiptests import Test

ROWS_AT_A_TIME=1
VHI=170
DVLO=0
DVHI=20
N_INJ=10

class ThresholdScanDataPort(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Threshold Scan','Measure s-curves for pixles')

    def run(self,pc,path):
        chipid=17
        of=open('%s/events.txt'%path,'w')
        self.total_steps=1 #FIXME
        self.current_step=0
        alpide.init(pc,chipid)
        pc.enable_parallel_port()
        pc.write_alpide_reg(chipid,0,6,5,VHI) # VPULSEH
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
        alpide.set_mask_all(pc,chipid,False)
        #for y in range(0,512,ROWS_AT_A_TIME):
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, 20 MHz, clustering: 0x1F9 -> disabled, 0x1FD -> enabled
        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,   200) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: delay strobe-pulse
        pc.write_alpide_reg(chipid,0,0,8,  2000) # FROMU Pulsing Register 2: pulse duration
        alpide.reset_readout(pc)
        pc.send_alpide_opcode(0xE4) # Pixel matrix reset
        #for y in range(0,512,ROWS_AT_A_TIME):
        #for y in range(0,10,ROWS_AT_A_TIME):
        total_hits=0
        # Activate pulse gating, set region masks to 0
        #alpide.set_regsel_register(pc,chipid,1,1)
        pc.write_alpide_reg(chipid,0,5,0,0x3) 
        for region in range(0, 32):
            pc.write_alpide_reg(chipid,region,4,0x8,0x0000)

        for y in [126,]:
            logging.info('... rows %d-%d...'%(y,y+ROWS_AT_A_TIME-1))
            alpide.set_pulsing_all(pc,chipid,False)
            for yy in range(y,y+ROWS_AT_A_TIME):
                alpide.set_pulsing_row(pc,chipid,yy,True)
            for dv in range(DVLO,DVHI+1):
                logging.info('   ... charge %d...'%dv)
                pc.write_alpide_reg(chipid,0,6,6,VHI-dv) # VPULSEL
                for i in range(N_INJ):
                     # Pulse double-pixel per double-pixel
                    for region in range(32):
                        logging.debug('   ... region %d...'%region)
                        for doublepix in range(16):
                            # Go through each double pixel
                            pc.write_alpide_reg(chipid,region,4,0x8,1<<doublepix)
                            #logging.info('Mask: {:016b}'.format(2**doublepix))
                            #logging.info('Region {:d}:  pulse gating reg: {:016b}'.format(region, pc.read_alpide_reg(chipid,region,4,0x8)))
                            #time.sleep(0.001) # wait 1 ms
                            pc.send_alpide_opcode(0x78)              # pulse!
                            #ev=pc.read_alpide_event(chipid)
                            raw=pc.read_parallel_port()[0]
                            ev=alpide.decode_event(raw,chipid)
                            of.write('# EVENT ROWS=%d-%d DV=%d\n'%(y,y+ROWS_AT_A_TIME,dv))
                            for xy in ev[3]:
                                of.write('%4d %3d\n'%xy)
                                total_hits+=1
                        # Reset registers for the region
                        pc.write_alpide_reg(chipid,region,4,0x8,0x0000)

        print('Total hits = {:d}'.format(total_hits))
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
            if s>m*m:
                s=(s-m*m)**0.5
            m/=den
            s/=den
        return m,s 

    def analyse(self,path):
        try:
            f=open('%s/events.txt'%path)
        except IOError:
            print('ERROR: File {:s}/events.txt could not be read!'.format(path))
            return {}
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
                thrmap[y,x]=m
                if m>DVHI:
                    print('WARNING: threshold out of bounds for pixel [%d, %d]: m=%e'%(y, x, m))
                thrshs.append(m)
        plt.figure()
        plt.xlabel('Threshold in DAC')
        plt.ylabel('Frequency')
        plt.title('Whole ALPIDE')
        plt.hist(thrshs,range(1,20))
        plt.savefig('%s/whole.png'%path)
        plt.close()

        plt.figure()
        plt.title('Threshold map')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        plt.pcolor(thrmap,vmin=0,vmax=15)
        plt.colorbar()
        plt.savefig('%s/thrmap.png'%path)
        plt.close()

        # For the threshold scan, consider only a subset neglecting the zeros
        subthrshs = [val for val in thrshs if val > 0 and val < DVHI]
        return {'threshold_mean': np.mean(subthrshs), 'threshold_stddev': np.std(subthrshs),
                'plot_threshold_distribution': '{:s}/whole.png'.format(self.path()),
                'plot_threshold_map'         : '{:s}/thrmap.png'.format(self.path())}


