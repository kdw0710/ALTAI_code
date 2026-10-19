import logging
from probecard import probecard
from probecard import alpide
import time
import numpy as np
import matplotlib.pyplot as plt
import os
from .test import Test

DT=0.001

# NAME, SUB_ADDR, OUTPUT MUX SELECTION, OFFSET
VDACS=[
  ('VRESETP', 1,4,0.4),
  ('VRESETD', 2,5,0.4),
  ('VCASP'  , 3,1,0.0),
  ('VCASN'  , 4,0,0.0),
  ('VPULSEH', 5,2,0.4),
  ('VPULSEL', 6,3,0.4),
  ('VCASN2' , 7,6,0.0),
  ('VCLIP'  , 8,7,0.0),
  ('VTEMP'  , 9,8,0.0)
]
IDACS=[
  ('IAUX2'  ,10,1),
  ('IRESET' ,11,0),
  ('IDB'    ,12,3),
  ('IBIAS'  ,13,2),
  ('ITHR'   ,14,5)
]

class DACScan(Test):
    def __init__(self):
        super(self.__class__,self).__init__('DAC Scan','Measures the linearity of the on-chip DACs')

    def run(self,pc,path):
        self.total_steps=18*256
        self.current_step=0
        chipid=17
        alpide.init(pc,chipid)
        for vdac in VDACS:
            logging.info('... %s...'%vdac[0])
            of=open('%s/%s.txt'%(path,vdac[0]),'w')
            of.write('# value\tvoltage [V]\n')
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0,data=vdac[2])
            for data in range(256):
                pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=vdac[1],data=data)
                v=pc.read_dacmonv()
                of.write('%d\t%f\n'%(data,v))
                time.sleep(DT)
            of.close()
        for idac in IDACS:
            logging.info('... %s...'%idac[0])
            of=open('%s/%s.txt'%(path,idac[0]),'w')
            of.write('# value\tcurrent [nA]\n')
            pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=0,data=idac[2]<<4)
            for data in range(256):
                pc.write_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=6,sub_addr=idac[1],data=data)
                i=pc.read_dacmoni()
                of.write('%d\t%f\n'%(data,i))
                time.sleep(DT)
            of.close()
        return True

    def analyse(self,path):
        # check correct starting and end points and INL
        # FIXME move ranges out of here
        results={}
        sumfig=plt.figure()
        plt.xlabel('Setting')
        plt.ylabel('Voltage [V] / Current [nA]')
        plt.xticks([0,64,128,192,255])
        for vdac in VDACS:
            results[vdac[0]]={}
            if not os.path.isfile('%s/%s.txt'%(path,vdac[0])):
                return {}
            data=np.loadtxt('%s/%s.txt'%(path,vdac[0]))
            if vdac[3]==0.0:
                results[vdac[0]]['start']=tuple(data[  0])
                results[vdac[0]]['end'  ]=tuple(data[239])
                fit=np.polyfit(data[0:240,0],data[0:240,1],1)
                fit_fn=np.poly1d(fit)
                inl=0
                for x in range(240):
                    inl=max(inl,abs(fit_fn(data[x][0])-data[x][1]))
                results[vdac[0]]['inl']=inl
            else:
                results[vdac[0]]['start']=tuple(data[  0])
                results[vdac[0]]['end'  ]=tuple(data[185])
                fit=np.polyfit(data[0:186,0],data[0:186,1],1)
                fit_fn=np.poly1d(fit)
                inl=0
                for x in range(186):
                    inl=max(inl,abs(fit_fn(data[x][0])-data[x][1]))
                results[vdac[0]]['inl']=inl
            plt.figure(sumfig.number)
            plt.plot([x[0] for x in data],[y[1] for y in data])
            plt.figure()
            plt.xlabel('Setting')
            plt.ylabel('Voltage [V]')
            plt.title('Scan of %s DAC'%vdac[0])
            plt.xticks([0,64,128,192,255])
            plt.plot([x[0] for x in data],[y[1] for y in data])
            x=np.linspace(0,255,256)
            #plt.plot(x,fit_fn(x))
            plt.savefig('%s/%s.png'%(path,vdac[0]))
            plt.close()
        for idac in IDACS:
            results[idac[0]]={}
            if not os.path.isfile('%s/%s.txt'%(path,idac[0])):
                return {}
            data=np.loadtxt('%s/%s.txt'%(path,idac[0]))
            results[idac[0]]['start']=tuple(data[  0])
            results[idac[0]]['end'  ]=tuple(data[214])
            fit=np.polyfit(data[0:215,0],data[0:215,1],1)
            fit_fn=np.poly1d(fit)
            inl=0
            for x in range(215):
                inl=max(inl,abs(fit_fn(data[x][0])-data[x][1]))
            results[idac[0]]['inl']=inl
            plt.figure(sumfig.number)
            plt.plot([x[0] for x in data],[y[1] for y in data])
            plt.figure()
            plt.xlabel('Setting')
            plt.ylabel('Current [nA]')
            plt.title('Scan of %s DAC'%idac[0])
            plt.xticks([0,64,128,192,255])
            plt.plot([x[0] for x in data],[y[1] for y in data])
            x=np.linspace(0,255,256)
            #plt.plot(x,fit_fn(x))
            plt.savefig('%s/%s.png'%(path,idac[0]))
            plt.close()
        plt.savefig('%s/all.png'%path)
        plt.close(sumfig)

        # Skim down results
        dacResults = {}
        for key in results.keys():
          dacResults[key] = {}
          dacResults[key]['inl'] = results[key]['inl']
          dacResults[key]['dA']  = results[key]['end'][1] - results[key]['start'][1]
          dacResults[key]['plot_dac_scan']  = '{:s}/{:s}.png'.format(self.path(),key)

        return {'dac_tests': dacResults, 'plot_sumfigure': '{:s}/all.png'.format(self.path())}

#    def accept(self,params):
#        # FIXME move ranges out of here
#        for vdac in VDACS:
#            if 

