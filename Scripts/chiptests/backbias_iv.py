from .test import Test
import re
import logging
from probecard import probecard
import time
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

class BackbiasIV(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Backbias IV scan','')

    def run(self,pc,path):
        #self.total_steps=601
        self.total_steps=31
        self.current_step=0
        pc.enable_por(False)
        pc.power_on(bb=True,vbb=0)
        of=open('%s/iv.txt'%path,'w')
        of.write('# Vbb (V)\tanalog (mA)\tdigital (mA)\tback-bias (uA)\tstatus\n')
        for self.current_step in range(self.total_steps):
            vbb=-6.0/(self.total_steps-1)*self.current_step
            logging.info('... VBB=%f'%vbb)
            pc.update_vpwell(vbb)
            if self.current_step % 15 == 0:
              time.sleep(2)
            else:
              time.sleep(0.1)
            i_a=pc.read_avdd_current()
            i_d=pc.read_dvdd_current()
            i_pwell=pc.read_pwell_current()*1000
            status=pc.power_status()
            of.write('%.2f\t%.2f\t%.2f\t%.2f\t%d\t%d\t%d\t%d\t%d\n'%(vbb,i_a,i_d,i_pwell,status[0],status[1],status[2],status[3],status[4]))
            if not status[0]:
                break
        pc.power_off()
        pc.enable_por() # jacobus 26/8/16
        return True 

    def analyse(self,path):
        sumfig=plt.figure()
        plt.xlabel('Back bias [V]')
        plt.ylabel('Current [mA]')
        try:
            data=np.loadtxt('%s/iv.txt'%(path))
            plt.plot([x[0] for x in data],[y[1] for y in data])
            plt.plot([x[0] for x in data],[y[2] for y in data])
            plt.plot([x[0] for x in data],[y[3]/1000 for y in data])
            plt.gca().invert_xaxis()
            plt.savefig('%s/iv.png'%(path))
            plt.close(sumfig)
            min_backbias_voltage=0
            i_pwell_3V=-1
            for x in data:
                if x[4]==1:
                    min_backbias_voltage=min(min_backbias_voltage,x[0])
                    if x[0]==-3.00 :
                        i_pwell_3V=x[3]/1000
                else:
                    if len(data)>1:
                        data=data[:-1]
                    break
            # Return minimum backbias voltage
            return {'min_backbias_voltage': min_backbias_voltage, 
                    'i_a'     : {'mean': np.mean([y[1] for y in data]), 'max': max([y[1] for y in data])},
                    'i_d'     : {'mean': np.mean([y[2] for y in data]), 'max': max([y[2] for y in data])},
                    'i_pwell' : {'mean': np.mean([y[3]/1000 for y in data]), 'max': max([y[3]/1000 for y in data]), '3V': i_pwell_3V},
                    'plot_iv' : '{:s}/iv.png'.format(self.path())}
        except Exception as e:
            print(e)
            plt.close()
            return {}
    
