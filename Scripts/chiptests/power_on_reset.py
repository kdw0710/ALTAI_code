import logging
import re
import time
from probecard import alpide
from probecard import probecard
import matplotlib.pyplot as plt
from chiptests import Test

class PowerOnReset(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Power-on reset test','Tests if power-on reset works')

    def run(self,pc,path):
        chipid=17
        pc.enable_por()
        #pc.disable_por()
        pc.set_chipid(chipid)
        time.sleep(0.2)
        of=open('%s/results.txt'%path,'w')
        of.write('# VDD\tVCASN\tVCASN2\tVCASN\'\tVCASN2\'\tI_A\tI_D\tI_BB\tstatus\n')
        for vdd in [1.5,1.55,1.6,1.65,1.7,1.75,1.8,1.85,1.9,1.95,2.0]:
            pc.power_off()
            time.sleep(0.5)
            pc.power_on(avdd=vdd,dvdd=vdd)
            time.sleep(0.1)
            i_a=pc.read_avdd_current()
            i_d=pc.read_dvdd_current()
            i_pwell=pc.read_pwell_current()*1000
            status=pc.power_status()[0]
            pc.write_alpide_reg(chipid,0,0,16,0x0070|chipid&0xF)
            #pc.write_alpide_reg(chipid,0,6,5,0x123)
            vcasn = vcasn2 = vcasnp = vcasn2p = 0
            try:
                vcasn =pc.read_alpide_reg(chipid,0,6,4) # VCASN
                vcasn2=pc.read_alpide_reg(chipid,0,6,7) # VCASN2
                pc.write_alpide_reg(chipid,0,6,4,0xF0) # VCASN
                pc.write_alpide_reg(chipid,0,6,7,0x01) # VCASN2
                vcasnp =pc.read_alpide_reg(chipid,0,6,4) # VCASN
                vcasn2p=pc.read_alpide_reg(chipid,0,6,7) # VCASN2
                of.write('%.2f\t%04X\t%04X\t%04X\t%04X\t%.2f\t%.2f\t%.2f\t%d\n'%(vdd,vcasn,vcasn2,vcasnp,vcasn2p,i_a,i_d,i_pwell,status))
            except probecard.CtrlChipIDMissmatch as e:
                of.write('%.2f\t%04X\t%04X\t%04X\t%04X\t%.2f\t%.2f\t%.2f\t%d - CHIPID missmatch\n'%(vdd,vcasn,vcasn2,vcasnp,vcasn2p,i_a,i_d,i_pwell,status))
                pc.purge_ctrl_port()
            working=(vcasn==0x0039 and vcasn2==0x0040 and vcasnp==0x00F0 and vcasn2p==0x0001 and status==1)
            logging.info('VDD=%.2f - POR %s'%(vdd,'working' if working else 'failing'))
        of.close()
        pc.power_off()
        return True

    def analyse(self,path):
        try:
            f=open('%s/results.txt'%path)
        except IOError:
            print('ERROR: File {:s}/results.txt could not be read!'.format(path))
            return {}
        vddlast=None
        vddmax=0
        for line in f:
            if line.startswith('#'):
                continue
            line=line.replace(' - CHIPID missmatch','')
            vdd,vcasn,vcasn2,vcasnp,vcasn2p,i_a,i_d,i_pwell,status=line.split()
            vdd    =float(vdd)
            vcasn  =int(vcasn  ,16)
            vcasn2 =int(vcasn2 ,16)
            vcasnp =int(vcasnp ,16)
            vcasn2p=int(vcasn2p,16)
            i_a    =float(i_a)
            i_d    =float(i_d)
            i_pwell=float(i_pwell)
            status =float(status)
            working=(vcasn==0x0039 and vcasn2==0x0040 and vcasnp==0x00F0 and vcasn2p==0x0001 and status==1)
            if working:
                vddmax=vdd
            else:
                break

        #if vddmax:
        #    print 'vddmax = %.2f'%vddmax
        #else:
        #    print 'vddmax = None'
        return {'vdd_max': vddmax}

    def analyse_old(self,path):
        f=open('%s/result.txt'%path)
        runningx,runningy,resetx,resety=[],[],[],[]
        vdd_last,por_last=None,None
        plt.figure()
        plt.xlabel('Time after power-up (s)')
        plt.ylabel('Digital supply current (mA)')
        plt.xscale('log')
        for line in f:
            if len(line.split())!=8:
                continue
            vdd,dt,por,i_a,i_d,i_pwell,vcasn,vcasnp=line.split() 
            if (vdd_last,por_last)!=(vdd,por):
                if vdd_last!=None:
                    if len(resetx)>0 and len(runningx)>0:
                        plt.plot([resetx[-1],runningx[0]],[resety[-1],runningy[0]],color='black',marker='')
                    plt.plot(resetx,resety,color='r',marker='o')
                    plt.plot(runningx,runningy,color='g',marker='o')
                runningx,runningy,resetx,resety=[],[],[],[]
                vdd_last,por_last=vdd,por
            if vcasn=='0039' and vcasnp=='0000':
                runningx.append(dt)
                runningy.append(i_d)
            else:
                resetx.append(dt)
                resety.append(i_d)
        reset=plt.Line2D((0,1),(0,0), color='r', marker='o')
        running=plt.Line2D((0,1),(0,0), color='g', marker='o')
        plt.legend([reset,running],['chip in reset','chip running'])
#          [label for i,label in enumerate(labels) if i in display]+['Simulation', 'Analytic'])
#
        plt.savefig('%s/timing.png'%path)
        plt.close()
