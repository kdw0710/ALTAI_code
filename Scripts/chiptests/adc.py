import logging
from probecard import probecard
from probecard import alpide
import time
import numpy as np
import matplotlib.pyplot as plt
import os
from .test import Test

DT=0.01
DT_CONV=0.005

class ADC(Test):
    def __init__(self):
        super(self.__class__,self).__init__('ADC','Measures the MSB of the ADC and two sample curves')

    def run(self,pc,path):
        chipid=17
        alpide.init(pc,chipid)

        # measure LSB:
        logging.info('... measuring LSB via ADCDAC...')
        of=open('%s/ADCDAC.txt'%(path),'w')
        of.write('# value\tvoltage [V]\tunscrambled value\n')
        pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x10,data=(0x1<<9|0x2<<6|0x0<<2|0x3<<0)); # super manual mode, AVSS
        pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0,data=9) # select ADCDAC
        for dac in range(2048): 
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x11,data=dac) # set ADCDAC DAC
            ret=pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x11)
            if dac!=ret:
                print(dac,ret)
            time.sleep(DT)
            v=pc.read_dacmonv()
            dacp=-1
            if dac%512<132:
              dacp=dac/512*264+dac%256
            elif 256<=dac%512 and dac%512<256+132:
              dacp=dac/512*264+264-dac%256  
            of.write('%d\t%f\t%d\n'%(dac,v,dacp))
        of.close()

        # mearure VTEMP
        logging.info('... measuring VTEMP using internal ADC...')
        of=open('%s/VTEMP.txt'%(path),'w')
        of.write('# DAC\tADC\n')
        pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x10,data=(0x1<<9|0x2<<6|0x5<<2|0x2<<0)); # manual mode, DACMONV
        pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0,data=8) # select VTEMP
        for dac in range(256):
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x09,data=dac) # det VTEMP DAC
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=0x00,data=0xFF20) # start conversion
            time.sleep(DT_CONV)
            adc=pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x1F)
            of.write('%d\t%d\n'%(dac,adc))
        of.close()
            
        # mearure IAUX2
        logging.info('... measuring IAUX2 using internal ADC...')
        of=open('%s/IAUX2.txt'%(path),'w')
        of.write('# DAC\tADC\n')
        pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x10,data=(0x1<<9|0x2<<6|0x6<<2|0x2<<0)); # manual mode, DACMONI
        pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0,data=1<<4) # select IAUX2
        for dac in range(256):
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x0A,data=dac) # det IAUX2 DAC
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=0x00,data=0xFF20) # start conversion
            time.sleep(DT_CONV)
            adc=pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0x24)
            of.write('%d\t%d\n'%(dac,adc))
        of.close()

        return True

    def analyse(self,path):
        results={}
        sumfig=plt.figure()
        if not os.path.isfile('%s/ADCDAC.txt'%(path)):
            print('ERROR: %s/ADCDAC.txt could not be found'%(path))
            return {}
        data=np.loadtxt('%s/ADCDAC.txt'%(path))
        print(len(data))
        if len(data)!=2048:
            print('ERROR: %s/ADCDAC.txt does not contain expected number of lines'%(path))
            return {}
        results['start']=tuple(data[  0])
        results['end'  ]=tuple(data[239])
        fit=np.polyfit(data[:,0],data[:,1],1)
        fit_fn=np.poly1d(fit)
        inl=0
        for x in range(240):
            inl=max(inl,abs(fit_fn(data[x][0])-data[x][1]))
        results['inl']=inl
        plt.xlabel('Setting')
        plt.ylabel('Voltage [V]')
        #plt.xticks([0,64,128,192,255])
        plt.xticks([0,256,512,768,1023])
        plt.plot([x[0] for x in data],[y[1] for y in data])
        plt.savefig('%s/ADCDAC.png'%(path))
        plt.close()

    #    # Skim down results
    #    dacResults = {}
    #    for key in results.keys():
    #      dacResults[key] = {}
    #      dacResults[key]['inl'] = results[key]['inl']
    #      dacResults[key]['dA']  = results[key]['end'][1] - results[key]['start'][1]
    #      dacResults[key]['plot_dac_scan']  = '{:s}/{:s}.png'.format(self.path(),key)

        return {'adc_tests': results, 'plot_sumfigure': '{:s}/ADCDAC.png'.format(self.path())}

#    def accept(self,params):
#        # FIXME move ranges out of here
#        for vdac in VDACS:
#            if 

