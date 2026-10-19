from .test import Test
import re
import logging
from probecard import probecard
import time
from datetime import datetime

class PowerTest(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Power Test','Tries to power the chip and measure its current consumption')

    def abort_on_failure(self):
      return True

    def run(self,pc,path):
        self.total_steps=20
        self.current_step=0
        chipid=17
        logging.info('Powering the chip w/o back bias')
        pc.enable_por(False)
        pc.set_chipid(chipid)
        time.sleep(0.2)
        pc.power_on(bb=False)
        of=open('%s/currents.txt'%path,'w')
        of.write('#time\tanalog (mA)\tdigital (mA)\tback-bias (uA)\tstatus\tstatus_avdd\tstatus_dvdd\tstatus_pwell\tstatus_sub\n')
        current_drawn=False
        for self.current_step in range(self.total_steps):
            i_a=pc.read_avdd_current()
            i_d=pc.read_dvdd_current()
            i_pwell=pc.read_pwell_current()*1000
            status=pc.power_status()
            if (i_a > 2 and i_d > 20):
                current_drawn=True
            #if i_pwell>50000.:
            #    status=False
            #if not status:
            #    pc.power_off()
            if self.current_step==0 or self.current_step==self.total_steps-1:
                logging.info('... analog current: %.2f mA, digital current: %.2f mA, pwell current: %f uA, %s'%(i_a,i_d,i_pwell,'power ok' if status[0] else 'power supply tripped'))
            of.write('%s\t%.2f\t%.2f\t%.2f\t%d\t%d\t%d\t%d\t%d\n'%(str(datetime.now()),i_a,i_d,i_pwell,status[0],status[1],status[2],status[3],status[4]))
            time.sleep(0.1)
        pc.power_off()
        pc.enable_por() # jacobus 26/8/16

        return status[0] and current_drawn
            
    def analyse(self,path):
        f=open('%s/currents.txt'%path)
        failure=False
        s_a=0
        s_d=0
        s_bb=0
        n=0
        for line in f.readlines()[3:]: # skip first 3 lines
            if not re.search('time',line):
                vs=line.split()
                i_a=float(vs[2])
                i_d=float(vs[3])
                i_bb=float(vs[4])
                status=int(vs[5])
                if status==0:
                    failure=True
                s_a+=i_a
                s_d+=i_d
                s_bb+=i_bb
                n+=1
        if n>0:
            return {'i_a':s_a/n,'i_d':s_d/n,'i_bb':s_bb/n/1000,'failure':failure}
        else:
            return None


