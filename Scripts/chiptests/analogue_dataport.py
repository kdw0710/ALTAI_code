import logging
from probecard import alpide
import re
import numpy as np
import matplotlib.pyplot as plt
import traceback
from chiptests import Test

ROWS_AT_A_TIME=1
VHI=170
VLO=100

class AnalogueScanDataPort(Test):
    def __init__(self,name='Analogue Scan DP',descr='Measure if all pixels respond to analogue pulsing'):
        super(AnalogueScanDataPort,self).__init__(name,descr)

    def init(self,pc,chipid):
        alpide.init(pc,chipid)
        pc.write_alpide_reg(chipid,0,6,5,VHI) # VPULSEH
        pc.write_alpide_reg(chipid,0,6,6,VLO) # VPULSEL
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
        #pc.write_alpide_reg(chipid,0,6,4,0) # VCASN
        # pc.write_alpide_reg(chipid,0,6,7,140) # VCASN2
        alpide.set_mask_all(pc,chipid,False)
        #        pc.write_alpide_reg(chipid,0,0,1,0x0021) # Triggered read-out, 20 MHz, clustering: 0x21 -> disabled, 0x25 -> enabled
        #        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        #        pc.write_alpide_reg(chipid,0,0,5,    40) # FROMU Configuration Register 2: strobe length
        #        pc.write_alpide_reg(chipid,0,0,6,     0) # FROMU Pulsing Register 1: delay strobe-pulse
        #        pc.write_alpide_reg(chipid,0,0,7,  2000) # FROMU Pulsing Register 2: pulse duration
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, 20 MHz, clustering: 0x1F9 -> disabled, 0x1FD -> enabled
        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,   200) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: delay strobe-pulse
        pc.write_alpide_reg(chipid,0,0,8,  2000) # FROMU Pulsing Register 2: pulse duration
        alpide.reset_readout(pc)
        pc.send_alpide_opcode(0xE4) # Pixel matrix reset
    def pulse_looop(self,pc,chipid,path):
        of=open('%s/events0.txt'%(path),'w')
        pc.purge_parallel_port()
        pc.enable_parallel_port()
        pc.purge_parallel_port()
        for y in range(0,512,ROWS_AT_A_TIME):
            #for y in range(0,1,ROWS_AT_A_TIME):
            logging.debug('... rows %d-%d...'%(y,y+ROWS_AT_A_TIME-1))
            alpide.set_pulsing_all(pc,chipid,False)
            for yy in range(y,y+ROWS_AT_A_TIME):
                alpide.set_pulsing_row(pc,chipid,yy,True)
            pc.send_alpide_opcode(0x78)              # pulse!
            raw=pc.read_parallel_port()[0]
            ev=alpide.decode_event(raw,chipid)
            of.write('# EVENT ROWS=%d-%d\n'%(y,y+ROWS_AT_A_TIME-1))
            for xy in ev[3]:
                of.write('%4d %3d\n'%xy)
        of.close()
        return True
    def run(self,pc,path):
        chipid=17
        self.init(pc,chipid)
        return self.pulse_looop(pc,chipid,path)

    def analyse(self,path):
        results={}
        try:
            f=open('%s/events0.txt'%(path))
        except IOError:
            print('ERROR: File {:s}/events0.txt could not be read!'.format(path))
            return {}
        (prevx, prevy) = (-1, -1)
        matrix=np.zeros((512,1024))
        matrixbroken=np.zeros((512,1024))
        for line in f:
            if re.match('#',line):
                continue
            try:
                x,y=map(int,line.split())
            except ValueError:
                print('ERROR: File {:s}/events0.txt contains line with unexpected format! <{:s}> instead of <x, y>'.format(path, line.strip()))
                return {}

            if prevx == x and prevy == y:
                matrixbroken[y,x]+=1
                prevx = -1
                prevy = -1
            else:
                (prevx, prevy) = (x,y)
                matrix[y,x]+=1

        dead=[]
        noisy=[]
        broken=[]
        for yx,n in np.ndenumerate(matrix):
            if n==0:
                dead.append(yx)
            if n>1 and matrixbroken[yx[0], yx[1]] == 0:
                noisy.append(yx)
        for yx,n in np.ndenumerate(matrixbroken):
            if n>0:
                broken.append(yx)


        plt.figure()
        plt.title('Hit map')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        plt.pcolor(matrix,vmin=0,vmax=2)
        plt.colorbar()
        plt.savefig('%s/hitmap0.png'%(path))
        plt.close()


        plt.figure()
        plt.title('Noise map')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        xs=[yx[1] for yx in noisy]
        ys=[yx[0] for yx in noisy]
        plt.scatter(xs,ys)
        plt.savefig('%s/noisemap0.png'%(path))
        plt.close()
        noisefile=open('%s/noisypixels0.txt'%(path),'w')
        noisefile.write('# x\ty\n')
        for yx in noisy:
            noisefile.write('%d\t%d\n'%(yx[1], yx[0]))
        noisefile.close()

        plt.figure()
        plt.title('Dead map')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        xs=[yx[1] for yx in dead]
        ys=[yx[0] for yx in dead]
        plt.scatter(xs,ys)
        plt.savefig('%s/deadmap0.png'%(path))
        plt.close()
        deadfile=open('%s/deadpixels0.txt'%(path),'w')
        deadfile.write('# x\ty\n')
        for yx in dead:
            deadfile.write('%d\t%d\n'%(yx[1], yx[0]))
        deadfile.close()

        plt.figure()
        plt.title('Broken map')
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        xs=[yx[1] for yx in broken]
        ys=[yx[0] for yx in broken]
        plt.scatter(xs,ys)
        plt.savefig('%s/brokenmap0.png'%(path))
        plt.close()
        brokenfile=open('%s/brokenpixels0.txt'%(path),'w')
        brokenfile.write('# x\ty\n')
        for yx in dead:
            brokenfile.write('%d\t%d\n'%(yx[1], yx[0]))
        brokenfile.close()

        results.update({'num_dead_pixels0': len(dead), 'num_noisy_pixels0': len(noisy),'num_broken_pixels0': len(broken),
                'plot_hit0': '{:s}/hitmap0.png'.format(self.path()),
                'plot_noise0': '{:s}/noisemap0.png'.format(self.path()),
                'plot_dead0': '{:s}/deadmap0.png'.format(self.path()),
                'plot_broken0': '{:s}/brokenmap0.png'.format(self.path())})

        return results

