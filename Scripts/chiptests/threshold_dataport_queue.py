import logging
import re
import numpy as np
import matplotlib.pyplot as plt
from probecard import alpide
import random
import time
import traceback
from probecard import probecard
from chiptests import Test

ROWS_AT_A_TIME=1
VHI=170
DVLO=0
DVHI=20
N_INJ=10
#N_INJ=1

class ThresholdScanDataPortQueue(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Threshold Scan Queue','Measure s-curves for pixles')

    def run(self,pc,path):
        chipid=17
        self.total_steps=1 #FIXME
        self.current_step=0
        alpide.init(pc,chipid)
        pc.enable_parallel_port()
        pc.purge_parallel_port()
        pc.write_alpide_reg(chipid,0,6,5,VHI) # VPULSEH
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
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

        # WAIT FOR BUSY mode
        # To be activated with new firmware
#        pc.write_pc_reg(probecard.PC_DCTRL_BUS, 15, 0)
#        pc.write_pc_reg(probecard.PC_DCTRL_BUS, 15, 1)
#        time.sleep(0.1)
#        pc.write_pc_reg(probecard.PC_DCTRL_BUS, 17, 1)
#        time.sleep(0.1)

        #########################################
        ## Set pulse gating registers
        ## This mask will be rotated and shifted automatically by FROMU cfg reg 1
        ## the rotation is done on the 16bit register specifying double columns in a region
        #alpide.set_regsel_register(pc,chipid,1,1)
        pc.write_alpide_reg(chipid,0,5,0,0x3) 

        #mask = 0b0000000000000001
        mask = 0b0001000100010001
        #mask = 0b0101010101010101
        #mask = 0b1111111111111111

        # Set the pulse gating mask (0x88 (region broadcast) or 0x8) to the given mask
        #for region in range(0, 32):
        #    pc.write_alpide_reg(chipid,region,4,0x8,0x0000)
        #for region in range(0, 32, 2):
        #    pc.write_alpide_reg(chipid,region,4,0x8,mask)

        # in all regions, set pulse gating mask
        pc.write_alpide_reg(chipid,0,4,0x88,mask)

        ## ENABLE ROTATE PULSE LINES
        #Chosen options: FROMU cfg. 1: disable busy monitoring, analog test pulse, enable test strobe, enable rotate pulse lines
        pc.write_alpide_reg(chipid,0,0,4,0x00E0) # FROMU Configuration Register 1

        nRotationDivisions = 4

        #########################################

        WAIT_REG_VALUE = 0x3000 #0xFFFA for 0.4 ms
        meanRowTime = 0
        startTime = time.time()
        memoryL = {'raw' : [], 'dv' : [], 'chipid': []} #, 'y' : [], 'pulseid' : []}

        pc.write_pc_reg(probecard.PC_DCTRL_BUS, 7, 0xFF)
        pc.write_pc_reg(probecard.PC_DCTRL_BUS, 7, 0x0)

        previous_trigger_count = pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=9)
        previous_strobe_count = pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=0xA)
        previous_event_count = pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=0xB)

        logging.info("busy register is {}".format(pc.read_pc_reg(probecard.PC_CFG_BUS, 30)))

        ################### DEBUG: See what happens after one pulse
        if False:
            pixelmap=np.zeros((32,32))
            #probed_rows = [0,1,2,3,126,127,128,129,254,255,256,257,382,383,384,385,508,509,510,511]
            probed_rows = [126]
            for y in probed_rows:
                alpide.set_pulsing_all(pc,chipid,False)
                alpide.set_mask_all(pc,chipid,True)
                for yy in range(y,y+ROWS_AT_A_TIME):
                    alpide.set_pulsing_row(pc,chipid,yy,True)
                    alpide.set_mask_row(pc,chipid,yy,False)
                for dv in range(DVLO,DVHI+1):
                    pc.write_alpide_reg(chipid,0,6,6,VHI-dv) # VPULSEL
                    for i in range(N_INJ):
                       for subregion in range(nRotationDivisions):
                            pc.send_alpide_opcode(0x78)              # pulse!
                            logging.info('Subregion {:d}:  pulse gating reg: {:016b}'.format(subregion, pc.read_alpide_reg(chipid,0,4,0x88)))

                            pc.write_pc_reg(probecard.PC_DCTRL_BUS, 6, 0xFF)
                            logging.info('OPcodes: {}, triggers sent: {}, not sent: {}. Number of wait executed: {}'.format(pc.read_pc_reg(probecard.PC_DCTRL_BUS, 11), pc.read_pc_reg(probecard.PC_DCTRL_BUS, 12), pc.read_pc_reg(probecard.PC_DCTRL_BUS, 13), pc.read_pc_reg(probecard.PC_DCTRL_BUS, 14)))
                            actual_trigger_count = pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=9)
                            actual_strobe_count = pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=0xA)
                            actual_event_count = pc.read_alpide_reg(chipid=chipid,rgn_addr=0,base_addr=0,sub_addr=0xB)                            
                            logging.info('triggers received: {}, strobe received {}, events received {}'.format(actual_trigger_count-previous_trigger_count, actual_strobe_count-previous_strobe_count, actual_event_count-previous_event_count))

                            previous_trigger_count = actual_trigger_count
                            previous_strobe_count =  actual_strobe_count 
                            previous_event_count =   actual_event_count 
                            
                            pc.write_pc_reg(probecard.PC_DCTRL_BUS, 7, 0xFF)
                            pc.write_pc_reg(probecard.PC_DCTRL_BUS, 7, 0x0)

                            logging.info("busy register is {}".format(pc.read_pc_reg(probecard.PC_CFG_BUS, 30)))

                            raw=pc.read_parallel_port()[0]
                            ev=alpide.decode_event(raw,chipid)
                            #logging.info('#### Chip answer after one pulse ####')
                            for (x,y) in ev[3]:
                                #logging.info('x=%4d y=%3d'%(x,y))
                                region = x // 32
                                xinRegion = x % 32
                                pixelmap[region][xinRegion] += 1
            plt.figure()
            plt.title('Pixel map')
            plt.xticks([i for i in range(0,32, 2)])
            plt.yticks([i for i in range(0,32, 1)])
            plt.xlim(0,32)
            plt.ylim(0,32)
            plt.ylabel("Region")
            plt.gca().invert_yaxis()
            plt.pcolor(pixelmap,vmin=0,vmax=200)
            plt.colorbar()
            plt.grid(True)
            plt.savefig('%s/pixelmap.png'%path)
            plt.close()
            exit()

        #probed_rows = [126,]
        probed_rows = range(0, 512)
        for y in probed_rows:
            probedPulses = 0
            logging.info('... rows %d-%d...'%(y,y+ROWS_AT_A_TIME-1))
            alpide.set_pulsing_all(pc,chipid,False)
            alpide.set_mask_all(pc,chipid,True)
            for yy in range(y,y+ROWS_AT_A_TIME):
                alpide.set_pulsing_row(pc,chipid,yy,True)
                alpide.set_mask_row(pc,chipid,yy,False)
            for dv in range(DVLO,DVHI+1):
                logging.debug('   ... charge %d...'%dv)
                pc.write_alpide_reg_queue(chipid,0,6,6,VHI-dv) # VPULSEL
                for i in range(N_INJ):
                    #logging.ninfo('      ... injection %d/%d...'%(i,N_INJ))
                    for region in range(32):
                        pc.write_alpide_reg_queue(chipid,region,2,0,0xF3)

                    for subregion in range(nRotationDivisions):
                        pc.send_alpide_opcode_queue(0x78)              # pulse!
                        probedPulses += 1
                        pc.write_pc_reg_queue(probecard.PC_DCTRL_BUS, 16, WAIT_REG_VALUE) # wait for x * 6.25ns, max = 0xFFFA (<65535) ~ 0.4 ms
            startTimeExec = time.time()
            # Trigger execution of queue

            pc.flush_alpide_queue()

            # Read data from parallel port
            readPulses = 0
            while readPulses < probedPulses:
                raw=pc.read_parallel_port()
                #print 'lenraw',len(raw)

                # Decode reading into n events
                logging.debug('Number of events: {:d}'.format(len(raw)))
                # TODO this should be propagated into analyse
                if len(raw)==0: break
                for rawev in raw:
                    #ev=alpide.decode_event(rawev,chipid)
                    memoryL['raw'].append(rawev)
                    memoryL['dv'].append(readPulses//(N_INJ*nRotationDivisions))
                    memoryL['chipid'].append(chipid)
                    #memoryL['y'].append(y)
                    #memoryL['pulseid'].append(readPulses)

                    total_hits+=1
                    readPulses+=1

            meanRowTime += (time.time() - startTimeExec)/len(probed_rows)

        logging.info('#### Pulsing+readout of one row took on average {} seconds. Expected time from waiting: {} s'.format(meanRowTime, probedPulses*(0.00000000625*WAIT_REG_VALUE)))
        logging.info('#### ALL THRESHOLDSCAN TESTS DONE IN MEMORY AFTER {:d} SECONDS ####'.format(int(time.time() - startTime)))
        # Write all data in one chunk to file
        import cPickle
        with open('%s/events.bin'%path, 'wb') as fp:
            cPickle.dump(memoryL, fp, protocol=2)
        logging.info('#### THRESHOLDSCAN RESULTS WRITTEN TO DISC AFTER {:d} SECONDS ####'.format(int(time.time() - startTime)))

        logging.info('Total hits = {:d}'.format(total_hits))
        return (total_hits>0)

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
        import pickle as cPickle
        try:
            with open('%s/events.bin'%path, 'rb') as fp:
                memoryL = cPickle.load(fp)
        except (IOError, EOFError):
            print('ERROR: File {:s}/events.txt could not be read!'.format(path))
            return {}

        # Note: We do the decoding of the events now in the analyse
        #       step, not online.
        #       The interpretation of the events is ported from the
        #       old threshold dataport scan

        # Go through all alpide events in file
        steps={}
        for index in range(len(memoryL['dv'])):
            # decode them
            try:
                event = alpide.decode_event(memoryL['raw'][index],memoryL['chipid'][index])
                dv = memoryL['dv'][index]
            except AssertionError as e:
                print('ERROR: event decoding failed with AssertionError')
                print(traceback.format_exc())
                return {}
            except IndexError as e:
                print('ERROR: event decoding failed with IndexError')
                print(traceback.format_exc())
                return {}

            # Create the first sublist for this dv
            if not dv in steps:
                steps[dv]=[1,[0]*(1<<19)]

            # Check if hits are present
            if(len(event[3])):
                # if yes, loop over all hits
                for xy in event[3]:
                    x,y=xy[0],xy[1]
                    steps[dv][1][y*1024+x]+=1
                # if no, mark it
                else:
                    steps[dv][0]+=1

        # scurve fit etc. code like in old threshold scan
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
        plt.hist(thrshs,range(1,DVHI))
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
        np.save('%s/thrmap.npy'%path,thrmap)
        plt.close()

        # For the threshold scan, consider only a subset neglecting the zeros
        subthrshs = [val for val in thrshs if val > 0 and val < DVHI]
        return {'threshold_mean': np.mean(subthrshs), 'threshold_stddev': np.std(subthrshs), 'threshold_npix': len(subthrshs),
                'stddev_mean_ratio': np.std(subthrshs)/np.mean(subthrshs),
                'plot_threshold_distribution': '{:s}/whole.png'.format(self.path()),
                'plot_threshold_map'         : '{:s}/thrmap.png'.format(self.path())}




