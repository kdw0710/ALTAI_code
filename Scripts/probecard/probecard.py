#!/usr/bin/env python3

try:
    import usb
except ImportError:
    usb = None
import time
import logging
import os
import configparser as ConfigParser
import errno

# TODO: move to config files?
CONTACT_TEST_DT=0.01

# ALPIDE PADS
# (MNEMONIC,POSITION,SELECT ADDRESS,RESULT REGISTER,RESULT BIT)
ALPIDE_PWELL  =[('PWELL%d'   %i,'G%02d'%(i*2  ) ,48+i,12,5+i) for i in range(4)]
ALPIDE_SUB    =[('SUB%d'     %i,'G%02d'%(1+i*2) ,54+i,12,2+i) for i in range(3)]
ALPIDE_SUB   +=[('SUB5'        ,'B20'           ,53  ,12,1  )                  ]
ALPIDE_AVDD   =[('AVDD%d'    %i,'F%02d'%i       ,16+i,10,8+i) for i in range(8)]
ALPIDE_AVSS   =[('AVSS%d'    %i,'E%02d'%i       ,24+i,10,  i) for i in range(8)]
ALPIDE_DVDD   =[('DVDD%d'    %i,'D%02d'%i       ,32+i,11,8+i) for i in range(8)]
ALPIDE_DVSS   =[('DVSS%d'    %i,'C%02d'%(i*2   ),40+i,11,0+i) for i in range(8)]
ALPIDE_CHIPID =[('CHIPID<%i>'%i,'C%02d'%(13-i*2),57+i,12,9+i) for i in range(7)]
ALPIDE_DATA   =[('DATA<%i>'  %i,'B%02d'%(16-i  ),64+i,13,8+i) for i in range(4)]
ALPIDE_BUSY   =[('BUSY'        ,'B17'           , 7  ,13,15 )                  ]
ALPIDE_CTRL   =[('CTRL'        ,'B12'           , 6  ,13,14 )                  ]
ALPIDE_DACMONI=[('DACMONI'     ,'B19'           ,15  ,13,13 )                  ]
ALPIDE_DACMONV=[('DACMONV'     ,'B18'           ,14  ,13,12 )                  ]
ALPIDE_SUB   +=[('SUB4'        ,'B00'           ,52  ,12,0  )                  ]
ALPIDE_DVDD33 =[('DVDD33'      ,'B01'           , 3  ,14,5  )                  ]
ALPIDE_MCLK_P =[('MCLK_P'      ,'B02'           ,12  ,13,0  )                  ]
ALPIDE_MCLK_N =[('MCLK_N'      ,'B03'           ,13  ,13,1  )                  ]
ALPIDE_RST_N  =[('RST_N'       ,'B04'           , 4  ,14,0  )                  ]
ALPIDE_POR_DIS=[('POR_DIS'     ,'B05'           , 5  ,14,1  )                  ]
ALPIDE_DCTRL_P=[('DCTRL_P'     ,'B06'           ,10  ,13,4  )                  ]
ALPIDE_DCTRL_N=[('DCTRL_N'     ,'B07'           ,11  ,13,5  )                  ]
ALPIDE_DCLK_P =[('DCLK_P'      ,'B08'           , 8  ,13,6  )                  ]
ALPIDE_DCLK_N =[('DCLK_N'      ,'B09'           , 9  ,13,7  )                  ]
ALPIDE_HDATA_P=[('HSDATA_P'    ,'B10'           , 1  ,13,2  )                  ]
ALPIDE_HDATA_N=[('HSDATA_N'    ,'B11'           , 2  ,13,3  )                  ]

ALPIDE_PADS=\
  ALPIDE_PWELL  +\
  ALPIDE_AVDD   +\
  ALPIDE_AVSS   +\
  ALPIDE_DVDD   +\
  ALPIDE_DVSS   +\
  ALPIDE_CHIPID +\
  ALPIDE_DATA   +\
  ALPIDE_BUSY   +\
  ALPIDE_CTRL   +\
  ALPIDE_DACMONI+\
  ALPIDE_DACMONV+\
  ALPIDE_SUB    +\
  ALPIDE_DVDD33 +\
  ALPIDE_MCLK_P +\
  ALPIDE_MCLK_N +\
  ALPIDE_RST_N  +\
  ALPIDE_POR_DIS+\
  ALPIDE_DCTRL_P+\
  ALPIDE_DCTRL_N+\
  ALPIDE_DCLK_P +\
  ALPIDE_DCLK_N +\
  ALPIDE_HDATA_P+\
  ALPIDE_HDATA_N

# minimal set for a test
# "all" (TODO: check+remove)
NEEDED_PADS=["PWELL", "AVDD", "AVSS", "DVDD", "DVSS"]

#NEEDED_PADS+=[pad[0] for pad in ALPIDE_PWELL]
#NEEDED_PADS+=[pad[0] for pad in ALPIDE_SUB]
NEEDED_PADS+=[pad[0] for pad in ALPIDE_CHIPID]
NEEDED_PADS+=[pad[0] for pad in ALPIDE_DATA]
NEEDED_PADS+=["BUSY","CTRL","DACMONI","DACMONV","RST_N","POR_DIS","DCTRL_P","DCTRL_N","DCLK_P","DCLK_N","HSDATA_P","HSDATA_N"]

# "minimum"
#NEEDED_PADS=["PWELL", "AVDD", "AVSS", "DVDD", "DVSS"]
#NEEDED_PADS+=[pad[0] for pad in ALPIDE_CHIPID]
#NEEDED_PADS+=["CTRL","RST_N","POR_DIS","DCTRL_P","DCTRL_N"]
#
#print "Minimal set of needles is: "
#print NEEDED_PADS

# PROBE CARD BUSSES
PC_CMD_BUS=0
PC_STS_BUS=1
PC_CFG_BUS=2
PC_HSDATA_BUS=3
PC_DCTRL_BUS=4
PC_DATA_BUS=5

class CtrlChipIDMissmatch(Exception):
    pass

class ProbeCard:
    def __init__(self,config):
        if usb is None:
            raise RuntimeError(
                "PyUSB is required only when connecting to the physical probe card. "
                "Install the 'pyusb' package to run hardware tests."
            )
        # parse probe card specific parameters (calibration+ID)
        calibration=ConfigParser.ConfigParser()
        script_path=os.path.dirname(os.path.realpath(__file__))
        calibration_filename='%s/../config/%s'%(script_path,config.get("DEFAULT","probecard_config"))
        calibration.read(calibration_filename)
        logging.info('Using calibration file "%s"'%calibration_filename)

        vid=int(calibration.get('DEFAULT','USB_VID'),16)
        pid=int(calibration.get('DEFAULT','USB_PID'),16)

        logging.info('Connecting to probecard (VID=%04X, PID=%04X)...'%(vid,pid))
        self.dev=usb.core.find(idVendor=vid,idProduct=pid)
        if self.dev is None:
            logging.error('No probe card found')
            raise Exception('No probe card found')
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
        self.dev.set_configuration(0)
        self.dev.set_configuration(1)
        self.cfg=self.dev.get_active_configuration()
        self.itf=self.cfg[(2,0)]
        self.epo=self.itf[0]
        self.epi=self.itf[1]
        self.epp=self.itf[2] # data from parallel port
        self.eps=self.itf[3] # data from high speed link
        self.epoqueue=[]
        self.nepi=0

        notworking =[a.strip() for a in calibration.get('Contact Logic','notworking' ).split(',')]
        replacement=[a.strip() for a in calibration.get('Contact Logic','replacement').split(',')]
        assert len(notworking)==len(replacement)
        for pad in notworking+replacement:
            assert pad in [pad[0] for pad in ALPIDE_PADS]
        self.contactfix=dict(zip(notworking,replacement))
        for pad in self.contactfix:
            logging.info('Contact logic for pad %s is hardwired to pad %s.'%(pad,self.contactfix[pad]))
        self.enable_parallel_port(False)
        n=self.purge_parallel_port()
        if n>0:
            logging.warning('Parallel port not empty at startup (%d bytes remaining).'%(n))
        self.enable_serial_port(False)
        n=self.purge_serial_port()
        if n>0:
            logging.warning('Serial port not empty at startup (%d bytes remaining).'%(n))
        n=self.purge_ctrl_port()
        if n>0:
            logging.warning('Control port not empty at startup (%d bytes remaining).'%(n))

        self.power_off() # low power

        # TODO: check USB serial number
        fpga_dna=self.read_fpga_dna()
        logging.info('FPGA DNA: 0x%015X'%fpga_dna)
        assert fpga_dna==int(calibration.get('ID','FPGA_DNA'),16)
        firmware_date_lo=self.read_pc_reg(PC_STS_BUS,19)
        firmware_date_hi=self.read_pc_reg(PC_STS_BUS,20)
        firmware_hash_lo=self.read_pc_reg(PC_STS_BUS, 0)
        firmware_hash_hi=self.read_pc_reg(PC_STS_BUS, 1)
        firmware_year ='20%02X'%(firmware_date_hi>>8&0xFF)
        firmware_month='%02X'%(firmware_date_hi>>0&0xFF)
        firmware_day  ='%02X'%(firmware_date_lo>>8&0xFF)
        firmware_hour ='%02X'%(firmware_date_lo>>0&0xFF)
        firmware_hash =firmware_hash_hi<<16|firmware_hash_lo
        logging.info('Probecard firmware: %08X, dated %s-%s-%s %s:00'%(firmware_hash,firmware_year,firmware_month,firmware_day,firmware_hour))
        assert firmware_year ==calibration.get('Firmware','Year')
        assert firmware_month==calibration.get('Firmware','Month')
        assert firmware_day  ==calibration.get('Firmware','Day'  )
        assert firmware_hour ==calibration.get('Firmware','Hour' )
        assert firmware_hash ==int(calibration.get('Firmware','Hash' ),16)

        # read calibration
        self.AVDD_DAC0     =calibration.getfloat('Supply Voltages','AVDD_DAC0'     )
        self.AVDD_dDACdV   =calibration.getfloat('Supply Voltages','AVDD_dDACdV'   )
        self.DVDD_DAC0     =calibration.getfloat('Supply Voltages','DVDD_DAC0'     )
        self.DVDD_dDACdV   =calibration.getfloat('Supply Voltages','DVDD_dDACdV'   )
        self.VPWELL_DAC0   =calibration.getfloat('Supply Voltages','PWELL_DAC0'    )
        self.VPWELL_dDACdV =calibration.getfloat('Supply Voltages','PWELL_dDACdV'  )
        self.AVDD_I0       =calibration.getfloat('Supply Currents','AVDD_I0'       )
        self.AVDD_dIdADC   =calibration.getfloat('Supply Currents','AVDD_dIdADC'   )
        self.DVDD_I0       =calibration.getfloat('Supply Currents','DVDD_I0'       )
        self.DVDD_dIdADC   =calibration.getfloat('Supply Currents','DVDD_dIdADC'   )
        self.PWELL_I0      =calibration.getfloat('Supply Currents','PWELL_I0'      )
        self.PWELL_dIdADC  =calibration.getfloat('Supply Currents','PWELL_dIdADC'  )
        self.DACMONV_V0    =calibration.getfloat('Monitoring ADCs','DACMONV_V0'    )
        self.DACMONV_dVdADC=calibration.getfloat('Monitoring ADCs','DACMONV_dVdADC')
        self.DACMONI_I0    =calibration.getfloat('Monitoring ADCs','DACMONI_I0'    )
        self.DACMONI_dIdADC=calibration.getfloat('Monitoring ADCs','DACMONI_dIdADC')

        self.ILIMIT_AVDD =calibration.getfloat('Current Limits','AVDD' )
        self.ILIMIT_DVDD =calibration.getfloat('Current Limits','DVDD' )
        self.ILIMIT_PWELL=calibration.getfloat('Current Limits','PWELL')

        self.write_pc_reg(PC_DATA_BUS,10,20) # parallel bus timeout

        # data port delays
        phase_data =calibration.getint('Signal Timing','phase_data' )
        delay_data0=calibration.getint('Signal Timing','delay_data0')
        delay_data1=calibration.getint('Signal Timing','delay_data1')
        delay_data2=calibration.getint('Signal Timing','delay_data2')
        delay_data3=calibration.getint('Signal Timing','delay_data3')
        assert phase_data |0x03==0x03
        assert delay_data0|0x1F==0x1F
        assert delay_data1|0x1F==0x1F
        assert delay_data2|0x1F==0x1F
        assert delay_data3|0x1F==0x1F
        self.write_pc_reg(PC_DATA_BUS, 0,phase_data)
        self.write_pc_reg(PC_DATA_BUS,24,delay_data1<<5|delay_data0)
        self.write_pc_reg(PC_DATA_BUS,25,delay_data3<<5|delay_data2)

        # DCTRL sampling phase (TODO: +sending?)
        phase_dctrl=calibration.getint('Signal Timing','phase_dctrl' )
        assert phase_dctrl|0x03==0x03
        self.write_pc_reg(PC_DCTRL_BUS,3,phase_dctrl)

        # TODO: clean up!
        print('SAMPLE PHASE=',self.read_pc_reg(PC_DATA_BUS,0))  # parallel bus sampling phase
        print('DELAYS=',self.read_pc_reg(PC_DATA_BUS,26),' ',self.read_pc_reg(PC_DATA_BUS,27))  # parallel bus sampling phase

        self.write_pc_reg(PC_DCTRL_BUS,15,0x01) # force internal busy to 0

    def conv32to8(self,word):
        return [word>>0&0xFF,word>>8&0xFF,word>>16&0xFF,word>>24&0xFF]
    def conv8to32(self,bytes):
        return bytes[3]<<24|bytes[2]<<16|bytes[1]<<8|bytes[0]<<0

    def write_pc_reg(self,mod_addr,sub_addr,data):
        assert mod_addr|0x0F  ==0x0F
        assert sub_addr|0xFF  ==0xFF
        assert data    |0xFFFF==0xFFFF
        self.epo.write([data>>0&0xFF,data>>8&0xFF,sub_addr,mod_addr|0x80])

    def read_pc_reg(self,mod_addr,sub_addr):
        assert mod_addr|0x0F==0x0F
        assert sub_addr|0xFF==0xFF
        self.epo.write([0x00,0x00,sub_addr,mod_addr])
        ret=self.epi.read(4)
        if ((ret[3]>>7)&0x1 == 1):
            raise RuntimeError("error while reading datafrom probecard: TODO: insert retry")
        return_value = ret[1]<<8|ret[0]
        logging.debug('read_pc_reg(mod_addr=%d,sub_addr=%d)=0x%04X'%(mod_addr,sub_addr,return_value))
        #print ("read_pc_reg {0:04X}{1:04X}{2:04X}{3:04X}".format(ret[3], ret[2], ret[1], ret[0]))
        return return_value

    def enable_parallel_port(self,enable=True):
        if enable:
           self.write_pc_reg(PC_DATA_BUS,9,1)
        else:
           self.write_pc_reg(PC_DATA_BUS,9,0)

    def enable_serial_port(self,enable=True):
        if (enable):
            self.write_pc_reg(PC_HSDATA_BUS,2,0x1D) # reset all subblocks
            self.write_pc_reg(PC_HSDATA_BUS,6,0xFFF) # reset all counters
            self.write_pc_reg(PC_HSDATA_BUS,6,0x000)
            self.write_pc_reg(PC_HSDATA_BUS,2,0x03) # IB, normal polarity, no PRBS check
            self.write_pc_reg(PC_HSDATA_BUS,4,0x02) # allow bit/word alignment
            self.write_pc_reg(PC_HSDATA_BUS,6,0xFFF) # reset all counters
            self.write_pc_reg(PC_HSDATA_BUS,6,0x000)
            self.write_pc_reg(PC_HSDATA_BUS,4,0x03) # enable readout, allow bit/word alignment
        else:
            self.write_pc_reg(PC_HSDATA_BUS,4,0x02) # disable readout, still allow bit/word alignment

    def read_fpga_dna(self):
        self.write_pc_reg(PC_CMD_BUS,6,0)
        time.sleep(0.1)
        self.write_pc_reg(PC_CMD_BUS,6,1)
        time.sleep(0.1)
        dna=0
        for i in range(4):
            dna=dna<<16|self.read_pc_reg(PC_STS_BUS,43-i)
        return dna&0x1FFFFFFFFFFFFFF

    def send_alpide_opcode(self,opcode):
        assert opcode|0xFF==0xFF
        self.write_pc_reg(PC_DCTRL_BUS,0,opcode<<8)

    def write_pc_reg_queue(self,mod_addr,sub_addr,data):
        assert mod_addr|0x0F  ==0x0F
        assert sub_addr|0xFF  ==0xFF
        assert data    |0xFFFF==0xFFFF
        self.epoqueue+=[data>>0&0xFF,data>>8&0xFF,sub_addr,mod_addr|0x80]

    def send_alpide_opcode_queue(self,opcode):
        assert opcode|0xFF==0xFF
        self.write_pc_reg_queue(PC_DCTRL_BUS,0,opcode<<8)

    def write_alpide_reg(self,chipid,rgn_addr,base_addr,sub_addr,data):
        logging.debug('write_alpide_reg(chipid=%02X,rgn_addr=%02X,base_addr=%02X,sub_addr=%02X,data=%04X)'%(chipid,rgn_addr,base_addr,sub_addr,data))
        self.write_alpide_reg_queue(chipid,rgn_addr,base_addr,sub_addr,data)
        ret=self.flush_alpide_queue()
        assert ret==[]

    def write_alpide_reg_queue(self,chipid,rgn_addr,base_addr,sub_addr,data):
        assert chipid   |0x7F==0x7F
        assert rgn_addr |0x1F==0x1F
        assert base_addr|0x07==0x07
        assert sub_addr |0xFF==0xFF
        addr=rgn_addr<<11|base_addr<<8|sub_addr
        #self.write_pc_reg(PC_DCTRL_BUS,1,addr)
        #self.write_pc_reg(PC_DCTRL_BUS,2,data)
        #self.write_pc_reg(PC_DCTRL_BUS,0,0x9C<<8|chipid)
        self.epoqueue+=[addr>>0&0xFF,addr>>8&0xFF,1,PC_DCTRL_BUS|0x80,
                        data>>0&0xFF,data>>8&0xFF,2,PC_DCTRL_BUS|0x80,
                        chipid      ,0x9C        ,0,PC_DCTRL_BUS|0x80]

    def flush_alpide_queue(self,chipid=None):
        assert self.nepi==0 or chipid!=None
        self.epo.write(self.epoqueue)
        self.epoqueue=[]
        read=[]
        while self.nepi!=0:
            ret=self.epi.read(self.nepi)
            self.nepi-=len(ret) # needs to be done before any exeption can be thrown...
            for i in range(0,len(ret),8):
                status=ret[i+1]<<8|ret[i+0]
                data=ret[i+5]<<8|ret[i+4]
                if status&0x7F!=chipid or status>>8&0x3F!=0x3F:
                    logging.error('STATUS: %04X (should be %04X)'%(status,0x3F<<8|chipid))
                if status&0x7F!=chipid:
                    raise CtrlChipIDMissmatch('status = 0x%04X (chipid=0x%02x), but chipid should be 0x%02X'%(status,status&0x7F,chipid))
                assert (status>>8)&0x3F==0x3F
                read.append(data)
                # FIXME: assert rest of status
        return read

    def read_alpide_reg_queue(self,chipid,rgn_addr,base_addr,sub_addr):
        assert chipid   |0x7F==0x7F
        assert rgn_addr |0x1F==0x1F
        assert base_addr|0x07==0x07
        assert sub_addr |0xFF==0xFF
        addr=rgn_addr<<11|base_addr<<8|sub_addr
        #self.write_pc_reg(PC_DCTRL_BUS,1,addr)
        #self.write_pc_reg(PC_DCTRL_BUS,0,0x4E<<8|chipid)
        #status=self.read_pc_reg(PC_DCTRL_BUS,4)
        #data  =self.read_pc_reg(PC_DCTRL_BUS,5)
        self.epoqueue+=[addr>>0&0xFF,addr>>8&0xFF,1,PC_DCTRL_BUS|0x80,
                        chipid      ,0x4E        ,0,PC_DCTRL_BUS|0x80,
                        0x00        ,0x00        ,4,PC_DCTRL_BUS     ,
                        0x00        ,0x00        ,5,PC_DCTRL_BUS     ]
        self.nepi+=8

    def read_alpide_reg(self,chipid,rgn_addr,base_addr,sub_addr):
        self.read_alpide_reg_queue(chipid,rgn_addr,base_addr,sub_addr)
        ret=self.flush_alpide_queue(chipid)
        assert len(ret)==1
        return ret[0]

    def purge_parallel_port(self):
        n=0
        try:
            while True:
                data=self.epp.read(1024,timeout=10)
                n+=len(data)
        except usb.core.USBError as err:
            if err.errno==errno.ETIMEDOUT:
                pass
            else:
                raise err
        logging.debug('Purged %d bytes from parallel port.'%n)
        return n

    def purge_serial_port(self):
        n=0
        try:
            while True:
                data=self.eps.read(1024,timeout=10)
                n+=len(data)
        except usb.core.USBError as err:
            if err.errno==errno.ETIMEDOUT:
                pass
            else:
                raise err
        logging.debug('Purged %d bytes from high-speed link.'%n)
        return n

    def purge_ctrl_port(self):
        n=0
        try:
            while True:
                data=self.epi.read(1024,timeout=10)
                n+=len(data)
        except usb.core.USBError as err:
            if err.errno==errno.ETIMEDOUT:
                pass
            else:
                raise err
        logging.debug('Purged %d bytes from control port - there were %d expected.'%(n,self.nepi))
        self.nepi=0
        return n

    def read_parallel_port(self):
        eventIndex = 0
        event = []
        eventList = []
        try:
            data=self.epp.read(1024*1024,timeout=100)
            logging.debug('read %d bytes:',len(data))
            assert len(data)%4==0
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                for i in range(0,len(data),4):
                    logging.debug('%04X: %02X-%02X-%02X-%02X'%(i,data[i],data[i+1],data[i+2],data[i+3]))
            #tmp=data
            #data=tmp[0:4]
            #for i in range(4,len(tmp),4):
            #    if tmp[i:i+4]!=data[-4:]:
            #        data+=tmp[i:i+4]
            #    else:
            #        logging.warning('duplicate 32bit word at addr %04X'%i)

            # Loop over all data bytes and write them event-wise into lists
            for i, inByte in enumerate(data):
                # Check input data and if OK,
                # use it to build the event
                if   eventIndex==3:
                    assert inByte==0x04
                elif eventIndex%4==3:
                    assert (inByte==0x00 or inByte==0x03)
                else:
                    event.append(inByte)

                eventIndex += 1

                # Check for event end marker
                # Put event to list of events
                if i%4==3 and inByte==0x03:
                    if logging.getLogger().isEnabledFor(logging.DEBUG):
                        for i in range(0,len(event),3):
                            logging.debug('%04X: %02X-%02X-%02X'%(i,event[i],event[i+1],event[i+2]))
                    eventList.append(event)
                    eventIndex = 0
                    event = []

            return eventList
        except usb.core.USBError as err:
            if err.errno==errno.ETIMEDOUT:
                #print 'Parallel port timeout - read %d events with lengths: '%len(eventList)
                #print map(len,eventList)
                #print len(event)
                return []
            else:
                raise err

    def read_parallel_port_old(self):
        try:
            data=self.epp.read(1024*1024)
            logging.debug('read %d bytes:',len(data))
            assert len(data)%4==0
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                for i in range(0,len(data),4):
                    logging.debug('%04X: %02X-%02X-%02X-%02X'%(i,data[i],data[i+1],data[i+2],data[i+3]))
            #tmp=data
            #data=tmp[0:4]
            #for i in range(4,len(tmp),4):
            #    if tmp[i:i+4]!=data[-4:]:
            #        data+=tmp[i:i+4]
            #    else:
            #        logging.warning('duplicate 32bit word at addr %04X'%i)
            payload=[]
            for i,b in enumerate(data):
                if   i==3:
                    assert b==0x04
                elif i==len(data)-1:
                    assert b==0x03
                elif i%4==3:
                    assert b==0x00
                else:
                    payload.append(b)
            return payload
        except usb.core.USBError as err:
            if err.errno==errno.ETIMEDOUT:
                return []
            else:
                raise err

    def read_parallel_port_tmp(self):
        #data=[]
        #while True:  # FIXME: this relies on a fast enought buffer creation and data sinking.
        #    tmp=self.epp.read(1024*1024)
        #    if logging.getLogger().isEnabledFor(logging.DEBUG): 
        #        logging.debug('read %d bytes:',len(tmp))
        #        for i in range(0,len(tmp),4):
        #            logging.debug('%04X: %02X-%02X-%02X-%02X'%(i,tmp[i],tmp[i+1],tmp[i+2],tmp[i+3]))
        #    assert len(tmp)%4==0
        #    #print len(tmp),tmp[-1]
        #    data+=tmp
        #    if len(tmp)>0 and tmp[-1]==0x03:
        #        break

        data=self.epp.read(1024*1024,timeout=100)
        if logging.getLogger().isEnabledFor(logging.DEBUG): 
            logging.debug('read %d bytes:',len(data))
            for i in range(0,len(data),4):
                logging.debug('%04X: %02X-%02X-%02X-%02X'%(i,data[i],data[i+1],data[i+2],data[i+3]))
        if len(data)==1024*1024:
            return False
        assert len(data)%4==0
        #print len(data),data[-1]
        payload=[]
        for i,b in enumerate(data):
            if   i==3:
                assert b==0x04
            elif i==len(data)-1:
                assert b==0x03
            elif i%4==3:
                assert b==0x00
            else:
                payload.append(b)
        return payload

    def read_parallel_port_old(self):
        data=self.epp.read(1024*1024)
        logging.debug('read %d bytes:',len(data))
        assert len(data)%4==0
        if logging.getLogger().isEnabledFor(logging.DEBUG): 
            for i in range(0,len(data),4):
                logging.debug('%04X: %02X-%02X-%02X-%02X'%(i,data[i],data[i+1],data[i+2],data[i+3]))
        payload=[]
        for i,b in enumerate(data):
            if   i==3:
                assert b==0x04
            elif i==len(data)-1:
                assert b==0x03
            elif i%4==3:
                assert b==0x00
            else:
                payload.append(b)
        return payload

    def read_serial_port(self):
        try:
            data=self.eps.read(1024*1024,timeout=10)
        except usb.core.USBError as err:
            if err.errno==errno.ETIMEDOUT:
                data=[]
            else:
                raise err
        assert len(data)%4==0
        if logging.getLogger().isEnabledFor(logging.DEBUG): 
            for i in range(0,len(data),4):
                logging.debug('%04X: %02X-%02X-%02X-%02X'%(i,data[i],data[i+1],data[i+2],data[i+3]))
        payload=[]
        for i,b in enumerate(data):
            if   i==3:
                assert b==0x04
            elif i==len(data)-1:
                assert b==0x03
            elif i%4==3:
                assert b==0x00
            else:
                payload.append(b)
        return payload
    
    def test_contacts(self):
        cs=[]
        self.power_off()
        self.write_pc_reg(PC_CFG_BUS,17,1)
        for pad in ALPIDE_PADS:
            if pad[0] in self.contactfix:
                cs.append(None)
            else:
                self.write_pc_reg(PC_CFG_BUS,24,pad[2])
                time.sleep(CONTACT_TEST_DT)
                cs.append(self.read_pc_reg(PC_STS_BUS,pad[3])>>pad[4]&0x1!=0x1)

        for pad in self.contactfix:
            cs[[p[0] for p in ALPIDE_PADS].index(pad)]=cs[[p[0] for p in ALPIDE_PADS].index(self.contactfix[pad])]

        logging.info("PWELL  "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_PWELL  ,cs[  : 4])])))
        logging.info("SUB    "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_SUB    ,cs[51:56])])))
        logging.info("AVDD   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_AVDD   ,cs[ 4:12])])))
        logging.info("AVSS   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_AVSS   ,cs[12:20])])))
        logging.info("DVDD   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DVDD   ,cs[20:28])])))
        logging.info("DVSS   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DVSS   ,cs[28:36])])))
        logging.info("CHIPID "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_CHIPID ,cs[36:43])])))
        logging.info("DATA   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DATA   ,cs[43:47])])))
        logging.info("BUSY   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_BUSY   ,cs[47:48])])))
        logging.info("CTRL   "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_CTRL   ,cs[48:49])])))
        logging.info("DACMONI"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DACMONI,cs[49:50])])))
        logging.info("DACMONV"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DACMONV,cs[50:51])])))
        logging.info("DVDD33 "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DVDD33 ,cs[56:57])])))
        logging.info("MCLK_P "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_MCLK_P ,cs[57:58])])))
        logging.info("MCLK_N "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_MCLK_N ,cs[58:59])])))
        logging.info("RST_N  "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_RST_N  ,cs[59:60])])))
        logging.info("POR_DIS"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_POR_DIS,cs[60:61])])))
        logging.info("DCTRL_P"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DCTRL_P,cs[61:62])])))
        logging.info("DCTRL_N"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DCTRL_N,cs[62:63])])))
        logging.info("DCLK_P "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DCLK_P ,cs[63:64])])))
        logging.info("DCLK_N "+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_DCLK_N ,cs[64:65])])))
        logging.info("HDATA_P"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_HDATA_P,cs[65:66])])))
        logging.info("HDATA_N"+(','.join(['%s:%d'%(pad[1],c) for pad,c in zip(ALPIDE_HDATA_N,cs[66:67])])))

        missing=0
        for query in NEEDED_PADS:
            contacted=0
            for index, item in enumerate([pad[0] for pad in ALPIDE_PADS]):
                if item.startswith(query):
                    if (cs[index] == 1):
                        contacted+=1
            if contacted==0:
                missing += 1

        logging.info("  -> Missing needles with respect to minimum set: %d"%missing)

        if missing == 0:
            for index, item in enumerate(cs):
                cs[index] = 1

        self.write_pc_reg(PC_CFG_BUS,24,0)
        return cs

    def set_avdd(self,voltage):
        dac=int(round(self.AVDD_DAC0+self.AVDD_dDACdV*voltage))
        assert 0<=dac and dac<4096 # TODO: check range!
        self.write_pc_reg(PC_CFG_BUS,0,dac)

    def set_dvdd(self,voltage):
        dac=int(round(self.DVDD_DAC0+self.DVDD_dDACdV*voltage))
        assert 0<=dac and dac<4096 # TODO: check range!
        self.write_pc_reg(PC_CFG_BUS,1,dac)

    def update_vpwell(self,voltage):
        self.set_vpwell(voltage,enqueue=True)
        self.write_pc_reg_queue(PC_CFG_BUS,10+1,4095)
        self.write_pc_reg_queue(PC_CMD_BUS, 0,0xF)
        self.write_pc_reg_queue(PC_CMD_BUS, 0,1<<10) # TODO:  bug fix
        self.write_pc_reg_queue(PC_DCTRL_BUS, 16, 0x7FFA) # wait for x * 6.25ns, max = 0xFFFA (<65535) ~ 0.4 ms
        self.set_pwell_current_limit(1,self.ILIMIT_PWELL,enqueue=True)
        self.flush_alpide_queue()

    def set_vpwell(self,voltage,enqueue=False):
        dac=int(round(self.VPWELL_DAC0+self.VPWELL_dDACdV*-voltage))
        if dac<0:
            dac=0
        assert 0<=dac and dac<4096 # TODO: check range!
        if enqueue:
            self.write_pc_reg_queue(PC_CFG_BUS,2,dac)
        else:
            self.write_pc_reg(PC_CFG_BUS,2,dac)


    def set_avdd_current_limit(self,step,current): # in mA
        assert 0<=step and step<=2
        dac=int(round((current-self.AVDD_I0)/self.AVDD_dIdADC))
        assert 0<=dac and dac<4095 # TODO: check range!
        self.write_pc_reg(PC_CFG_BUS,4+step,dac)

    def set_dvdd_current_limit(self,step,current):
        assert 0<=step and step<=2
        dac=int(round((current-self.DVDD_I0)/self.DVDD_dIdADC))
        assert 0<=dac and dac<4095 # TODO: check range!
        self.write_pc_reg(PC_CFG_BUS,7+step,dac)

    def set_pwell_current_limit(self,step,current,enqueue=False):
        assert 0<=step and step<=2
        dac=int(round((current-self.PWELL_I0)/self.PWELL_dIdADC))
        assert 0<=dac and dac<4095
        if enqueue:
            self.write_pc_reg_queue(PC_CFG_BUS,10+step,dac)
        else:
            self.write_pc_reg(PC_CFG_BUS,10+step,dac)

    def disable_pwell_current_limit(self,step,enqueue=False):
        if enqueue:
            self.write_pc_reg_queue(PC_CFG_BUS,10+step,4095)
        else:
            self.write_pc_reg(PC_CFG_BUS,10+step,4095)

    def read_avdd_current(self):
        adc=self.read_pc_reg(PC_STS_BUS,2)
        logging.debug("analogue ADC=%d"%adc)
        return self.AVDD_I0+self.AVDD_dIdADC*adc

    def read_dvdd_current(self):
        adc=self.read_pc_reg(PC_STS_BUS,3)
        return self.DVDD_I0+self.DVDD_dIdADC*adc

    def read_pwell_current(self):
        adc=self.read_pc_reg(PC_STS_BUS,5)
        logging.debug("pwell ADC=%d"%adc)
        return self.PWELL_I0+self.PWELL_dIdADC*adc

    def read_dacmonv(self):
        adc=self.read_pc_reg(PC_STS_BUS,7)
        return self.DACMONV_V0+self.DACMONV_dVdADC*adc

    def read_dacmoni(self):
        adc=self.read_pc_reg(PC_STS_BUS,8)
        return self.DACMONI_I0+self.DACMONI_dIdADC*adc


    def power_on(self,bb=False,vbb=-6.0,avdd=1.8,dvdd=1.8):
        if bb:
            self.write_pc_reg(PC_CFG_BUS, 17,4)   # PWELL=SUB=PWELL_LDO
        else:
            self.write_pc_reg(PC_CFG_BUS, 17,0)   # PWELL=SUB=GND

        self.write_pc_reg(PC_CFG_BUS,25, 250) # x ms delay between T=0 and VDD on
        self.write_pc_reg(PC_CFG_BUS,16, 100) # x ms delay between VDD on and config mode

        self.set_dvdd(dvdd)
        self.set_avdd(avdd)
        self.set_vpwell(vbb)

        self.write_pc_reg(PC_CMD_BUS, 0,0xF)
        self.write_pc_reg(PC_CMD_BUS, 0,1<<10) # TODO:  bug fix

        for step in range(3):
            self.set_avdd_current_limit(step,self.ILIMIT_AVDD)
            self.set_dvdd_current_limit(step,self.ILIMIT_DVDD)
            if step>0:
                self.set_pwell_current_limit(step,self.ILIMIT_PWELL)
            else:
                self.disable_pwell_current_limit(step)
        # POWER ON
        self.write_pc_reg(PC_CMD_BUS,1,1<<0)
        self.write_pc_reg(PC_CMD_BUS,1,1<<10) # TODO: bugfix

    def power_off(self): # power off the chip!
        self.write_pc_reg(PC_CMD_BUS,1,1<<2)
        self.write_pc_reg(PC_CMD_BUS,1,1<<10) # TODO: bugfix

    def set_chipid(self,chipid):
        assert chipid|0x7F==0x7F
        self.write_pc_reg(PC_CFG_BUS,23,chipid)
        self.write_pc_reg(PC_CMD_BUS,2,1<<1)
        # to be removed after CMD_BUS bug fix TODO
        self.write_pc_reg(PC_CMD_BUS,2,1<<10) #TODO

    def power_status(self):
        # ret=self.read_pc_reg(PC_STS_BUS,9)
        # if ret==0xAFFE or ret==0xCAFE:
        #    return True
        # else:
        #    return False
        ret_avdd=self.read_pc_reg(PC_STS_BUS,25)
        ret_dvdd=self.read_pc_reg(PC_STS_BUS,26)
        ret_pwell=self.read_pc_reg(PC_STS_BUS,27)
        ret_sub=self.read_pc_reg(PC_STS_BUS,28)

        if (ret_avdd>>15 & 1) or (ret_dvdd>>15 & 1) or (ret_pwell>>15 & 1) or (ret_sub>>15 & 1):
            #print(">>trip Current \t>> avdd {0:3.2f},\t  dvdd {1:3.2f},\t pwell {2:3.2f},\t  sub {3:3.2f}".format((ret_avdd & 0xFFF)*PC_ADC_AVDD[1],(ret_dvdd & 0xFFF)*PC_ADC_DVDD[1],(ret_pwell & 0xFFF)*PC_ADC_PWELL[1],(ret_sub & 0xFFF)*PC_ADC_SUB[1]))
            #print(">>trip Chanel  \t>> avdd {0},\t  dvdd {1},\t pwell {2},\t  sub {3}".format((ret_avdd>>15 & 1), (ret_dvdd>>15 & 1), (ret_pwell>>15 & 1), (ret_sub>>15 & 1)))
            return [False, (ret_avdd>>15 & 1), (ret_dvdd>>15 & 1), (ret_pwell>>15 & 1), (ret_sub>>15 & 1)]
        else:
            return [True, 0, 0, 0, 0]

    def enable_por(self,enable=True):
        self.write_pc_reg(PC_CFG_BUS,27,0 if enable else 2)
