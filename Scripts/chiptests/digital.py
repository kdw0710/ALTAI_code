import logging
import re
import numpy as np
from chiptests import Test
import matplotlib.pyplot as plt
from probecard import alpide

NITERATIONS=10

class DigitalScan(Test):
    def __init__(self,name='Digital Scan',descr='Measure if all pixels respond to digital pulsing'):
        super(DigitalScan,self).__init__(name,descr)

    def init(self,pc,chipid):
        alpide.init(pc,chipid)
        pc.write_alpide_reg(chipid,0,6,4,0x0000) # VCASN=0
        pc.write_alpide_reg(chipid,0,6,13,0x0000) # IBIAS=0
        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,   200) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: pulse-strobe delay
        pc.write_alpide_reg(chipid,0,0,8,  20) # FROMU Pulsing Register 2: pulse length
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, clustering: FD, no clustering F9

    def run_test(self,pc,chipid,path):
        pc.enable_parallel_port()
        pc.purge_parallel_port()
        of=open('%s/events.dat'%path,'wb')
        # Check each meb entry seperately
        allbad=set()
        alpide.reset_matrix(pc)
        alpide.set_mask_all(pc,chipid,True)
        alpide.set_pulsing_all(pc,chipid,False)
        for regions in [range(0,8),range(8,16),range(16,24),range(24,32)]:
            for region in range(32):
                if region in regions:
                    pc.write_alpide_reg(chipid,region,3,0,0x0000) # enable all columns
                else:
                    pc.write_alpide_reg(chipid,region,3,0,0xFFFF) # disable all columns
            for meb in range(3):
                logging.info('Regions %s, MEB slice no. %d:'%(regions,meb))
                pc.write_alpide_reg(chipid,0,0,4,0x0040|([0x6,0x5,0x3][meb])) # FROMU Configuration Register 1: disable busy monitoring, digital test pulse, enable test strobe
                alpide.reset_readout(pc)
                # 1) try to interatively mask bad pixels, i.e. those that would disable double columns
                pixel_mask=set()
                for i in range(NITERATIONS):
                    logging.info('  Interation no. %d: %d pixel(s) masked'%(i+1,len(pixel_mask)))
                    for region in regions:
                        pc.write_alpide_reg(chipid,region,3,0,0x0000) # enable all columns
                    bad=set()
                    for pulsing in [True,False]:
                        alpide.set_pulsing_all(pc,chipid,pulsing)
                        for mask in [False,True]:
                            alpide.set_mask_all(pc,chipid,mask)
                            for x,y in pixel_mask:
                                logging.debug('   Masking pixel x=%d, y=%d'%(x,y))
                                alpide.set_mask_xy(pc,chipid,x,y)
                            alpide.reset_matrix(pc)
                            alpide.pulse(pc)
                            busyon=pc.read_parallel_port_tmp()
                            raw   =pc.read_parallel_port_tmp()
                            if raw==False:
                                logging.warn('   -> event too large, stopping test')
                                return False
                            pc.purge_parallel_port() # possible busy offs
                            ev=alpide.decode_event(raw,chipid)
                            logging.info('    Pulsing=%s, Mask=%s: %d pixels fired.'%(pulsing,mask,len(ev[3])))

                            of.write(('# EVENT pulsing=%d mask=%d regions=%s meb=%d length=%d\n' % (pulsing, mask, list(regions), meb, len(raw))).encode('ascii'))
                            of.write(('# masked pixels: [' + ','.join('(%d,%d)' % xy for xy in pixel_mask) + ']\n').encode('ascii'))
                            of.write(bytes(raw))
                            of.write(b'\n')

#                            f=open('event.txt','a')
#                            for xy in ev[3]:
#                                f.write('%d %d\n'%xy);
#                            f.write('\n\n')
#                            f.close()

                            last_xy=None
                            for xy in ev[3]:
                                if mask==True or pulsing==False:
                                    logging.debug('   Unwanted pixel at x=%d, y=%d'%xy)
                                    allbad.add(xy)
                                if last_xy==xy:
                                    logging.debug('   Bad pixel at x=%d, y=%d'%xy)
                                    bad.add(xy)
                                    allbad.add(xy)
                                last_xy=xy
                    logging.info('    ... %d bad pixels found.'%len(bad))
                    logging.info('    ... %d bad pixels are new.'%len(bad-pixel_mask))
                    logging.info('    ... %d bad pixels were there before.'%len(bad&pixel_mask))
                    if len(bad-pixel_mask)==0:
                        logging.info('    ... No new bad pixel appeared. Stopping here.')
                        break
                    pixel_mask|=bad
                    if (i==NITERATIONS-1):
                        logging.info('    ... Maximum number of trials reached. Stopping here.')
 
            logging.info('Total of %d bad pixels found.'%len(allbad))
        ## Mask all pixels that were bad in any of the MEBs or were firing while masked or not pulsed:
        #alpide.set_pulsing_all(pc,chipid,True)
        #alpide.set_mask_all(pc,chipid,False)
        #for xy in allbad:
            #    alpide.set_mask_xy(pc,*xy)
        #for meb in range(3):
        #    logging.info('MEB slice no. %d:'%meb)

        of.close()
        return True
    def run(self,pc,path):
        chipid=17
        self.init(pc,chipid)
        return self.run_test(pc,chipid,path)

    def plot_map(self,path,fname,title,pixels,invert=False):
        plt.figure()
        plt.title(title)
        #plt.xlabel('X')
        #plt.ylabel('Y')
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        if invert:
            tmp=[]
            for y in range(512):
                for x in range(1024):
                    tmp.append((x,y))
            pixels=list(set(tmp)-set(pixels))
        xs=[xy[0] for xy in pixels]
        ys=[xy[1] for xy in pixels]
        plt.scatter(xs,ys)
        plt.savefig('%s/%s'%(path,fname))
        plt.close()

    def analyse(self,path):
        try:
          f=open('%s/events.dat'%path,'rb')
        except IOError:
            print('ERROR: File {:s}/events.dat could not be read!'.format(path))
            return {}

        chipid=17
        # These are dicts of dicts of arrays, indexed by regions, meb
        unmaskable={} # fire if mask=1 pulse=1
        pulsable  ={} # do fire if mask=0 pusle=1
        stuck     ={} # fire if mask=0 pulse=0
        bad       ={} # fire if mask=1 pulse=0 (OK!?)
        masked    ={} # pixels that were recursively masked to achieve self.result
        nlines=0
        while f:
            header = f.readline()
            if header == b'' and nlines == 0:
                return {}
            elif header == b'':
                break
            nlines += 1
            header = header.decode('ascii', errors='replace')
            pulsing = int(re.search(r'pulsing=(\d)', header).group(1))
            mask = int(re.search(r'mask=(\d)', header).group(1))
            meb = int(re.search(r'meb=(\d)', header).group(1))
            length = int(re.search(r'length=(\d+)', header).group(1))
            regions = [int(x) for x in re.search(r'regions=\[(\d+(, \d+)*)\]', header).group(1).split(',')]
            pixel_mask = f.readline()
            if pixel_mask == b'':
                return {}
            pixel_mask = pixel_mask.decode('ascii', errors='replace')

            if not meb in unmaskable:
                unmaskable[meb]={}
                pulsable  [meb]={}
                stuck     [meb]={}
                bad       [meb]={}
                masked    [meb]={}
            if not str(regions) in unmaskable[meb]:
                unmaskable[meb][str(regions)]=[]
                pulsable  [meb][str(regions)]=[]
                stuck     [meb][str(regions)]=[]
                bad       [meb][str(regions)]=[]
                masked    [meb][str(regions)]=[]
   
            # masked pixels: []
            pixel_mask = re.search(r'masked pixels: \[(.*)\]', pixel_mask).group(1)
            if len(pixel_mask) > 0:
                masked[meb][str(regions)] = [
                    tuple(map(int, x.split(',')))
                    for x in pixel_mask[1:-1].split('),(')
                ]
            else:
                masked[meb][str(regions)] = []
            raw = list(f.read(length))
            if len(raw) != length:
                return {}
            try:
                ev=alpide.decode_event(raw,chipid)
            except:
                return {}
#            print header
#            for x,y in ev[3]:
#                print x,y
#            print ''
            if mask==1 and pulsing==1:
                unmaskable[meb][str(regions)]=ev[3]
            elif mask==0 and pulsing==1:
                pulsable[meb][str(regions)]=ev[3]
            elif mask==0 and pulsing==0:
                stuck[meb][str(regions)]=ev[3]
            elif mask==1 and pulsing==0:
                bad[meb][str(regions)]=ev[3]
            f.readline()

        results={}
        unmaskable_all=[]
        unpulsable_all  =[]
        stuck_all     =[] 
        bad_all       =[]
        masked_all    =[]
        for meb in range(3):
            unmaskable_meb=[]
            pulsable_meb=[]
            unpulsable_meb=[(x,y) for x in range(1024) for y in range(512)]
            stuck_meb=[]
            bad_meb=[]
            masked_meb=[]
            try:
                for hits in unmaskable[meb].values():
                    unmaskable_meb+=hits
                for hits in pulsable[meb].values():
                    pulsable_meb+=hits
                for hits in stuck[meb].values():
                    stuck_meb+=hits
                for hits in bad[meb].values():
                    bad_meb+=hits
                for pixels in masked[meb].values():
                    masked_meb+=pixels
            except:
                return {}
            unmaskable_meb=list(set(unmaskable_meb))
            pulsable_meb  =list(set(pulsable_meb  ))
            unpulsable_meb=list(set(unpulsable_meb)-set(pulsable_meb))
            stuck_meb     =list(set(stuck_meb     ))
            bad_meb       =list(set(bad_meb       ))
            masked_meb    =list(set(masked_meb    ))
            self.plot_map(path,'unmaskable-meb%d.png'%meb,'Unmaskable pixels (fire if pulsed but also masked) MEB%d'      %meb,unmaskable_meb)
            self.plot_map(path,'unpulsable-meb%d.png'%meb,'Unpulsable pixels (do not fire if not maksed but pulsed) MEB%d'%meb,unpulsable_meb)
            self.plot_map(path,'stuck-meb%d.png'     %meb,'Stuck pixels (fire if not masked and not pulsed) MEB%d'        %meb,stuck_meb)
            self.plot_map(path,'bad-meb%d.png'       %meb,'Bad pixels (fire if masked and not pulsed) MEB%d'              %meb,bad_meb)
            self.plot_map(path,'masked-meb%d.png'    %meb,'Masked pixels (due to failure) MEB%d'                          %meb,masked_meb)
            results['unmaskable-meb%d'%meb]=len(unmaskable_meb)
            results['unpulsable-meb%d'%meb]=len(unpulsable_meb)
            results['stuck-meb%d'     %meb]=len(stuck_meb)
            results['bad-meb%d'       %meb]=len(bad_meb)
            results['masked-meb%d'    %meb]=len(masked_meb)
            unmaskable_all+=unmaskable_meb
            unpulsable_all+=unpulsable_meb
            stuck_all     +=stuck_meb
            bad_all       +=bad_meb
            masked_all    +=masked_meb
        unmaskable_all=list(set(unmaskable_all))
        unpulsable_all=list(set(unpulsable_all))
        stuck_all     =list(set(stuck_all     ))
        bad_all       =list(set(bad_all       ))
        masked_all    =list(set(masked_all    ))
        self.plot_map(path,'unmaskable-all.png','Unmaskable pixels (fire if pulsed but also masked)'      ,unmaskable_all)
        self.plot_map(path,'unpulsable-all.png','Unpulsable pixels (do not fire if not maksed but pulsed)',unpulsable_all)
        self.plot_map(path,'stuck-all.png'     ,'Stuck pixels (fire if not masked and not pulsed)'        ,stuck_all)
        self.plot_map(path,'bad-all.png'       ,'Bad pixels (fire if masked and not pulsed)'              ,bad_all)
        self.plot_map(path,'masked-all.png'    ,'Masked pixels (due to failure)'                          ,masked_all)
        results['unmaskable-all']=len(unmaskable_all)
        results['unpulsable-all']=len(unpulsable_all)
        results['stuck-all'     ]=len(stuck_all)
        results['bad-all'       ]=len(bad_all)
        results['masked-all'    ]=len(masked_all)
        return results
