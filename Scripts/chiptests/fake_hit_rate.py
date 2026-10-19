import logging
from probecard import alpide
import re
import numpy as np
import matplotlib.pyplot as plt
from chiptests import Test

NEVENTS=10000
#STROBE_LENGTHS=[1,2,5,10,20,50,100,200,500,1000,2000,5000,10000,20000,50000]
#STROBE_LENGTHS=[20,40,200,400] # 500 ns, 1 us, 5 us, 10 us
STROBE_LENGTHS=[400] # 10 us
#STROBE_LENGTHS=map(lambda i:int(round(40000**(i/99.0))),range(100))
NMASK=[0,1,2,5,10,100]

class FakeHitRate(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Fake Hit Rate','Measures cosmics if everything goes well')

    def run(self,pc,path):
        chipid=17
        of=open('%s/events.txt'%path,'w')
        self.total_steps=1 #FIXME
        self.current_step=0
        alpide.init(pc,chipid)
        pc.purge_parallel_port()
        pc.enable_parallel_port()
        pc.write_alpide_reg(chipid,0,6,2,147) # VRESETD
        #pc.write_alpide_reg(chipid,0,6,4,0) # VCASN
        # pc.write_alpide_reg(chipid,0,6,7,140) # VCASN2
        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, 20 MHz, clustering: 0x1F9 -> disabled, 0x1FD -> enabled
        pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        alpide.reset_readout(pc)
        alpide.set_pulsing_all(pc,chipid,False)

        of.write('# MASKED BAD PIXELS: \n')
        for sl in STROBE_LENGTHS:
            alpide.set_mask_all(pc,chipid,False)
            for region in range(32):
                pc.write_alpide_reg(chipid,region,3,0,0x0000) # enable all columns
            logging.info('... strobe length: %d ns...'%(sl*25))
            of.write('# STROBE LENGTH %d\n'%sl)
            pc.write_alpide_reg(chipid,0,0,5,sl) # FROMU Configuration Register 2: strobe length (x25ns)
            hits_tot={}
            for nmask in NMASK:
                for _,(x,y) in list(reversed(sorted([(n,xy) for xy,n in hits_tot.items()])))[:nmask]:
                    alpide.set_mask_xy(pc,chipid,x,y)
                logging.info('... masking %d most noisy pixel(s)...'%nmask)
                of.write('# MASKED NOISY PIXELS: \n') #TODO
                alpide.reset_matrix(pc)
                hits={}
                for i in range(NEVENTS):
                    if i%1000==0:
                        logging.debug('... event %d/%d...'%(i+1,NEVENTS))
                    alpide.trigger(pc)
                    raw=pc.read_parallel_port()[0]
                    ev=alpide.decode_event(raw,chipid)
                    if len(ev[3]) > 50000:
                        logging.warning('... %d hits in a single event. Aborting.')
                        of.close()
                        return False
                    of.write('# EVENT %d\n'%(i+1))
                    for xy in ev[3]:
                         if xy in hits:
                             hits[xy]+=1
                         else:
                             hits[xy]=1
                         of.write('%4d %3d\n'%xy)
                for xy,n in hits.items():
                    if xy in hits_tot:
                        hits_tot[xy]+=n
                    else:
                        hits_tot[xy]=n
                    
                logging.info('... %d hits in %d events. Distributed over %d pixels.'%(sum(hits.values()),NEVENTS,len(hits)))
        of.close()
        return True

    def analyse_one(self,path,matrix,nev,sl,masked,setting):
        nmask=len(masked) if masked!=None else NMASK[setting]
            
        matrix/=nev
        #x=np.array()=
        fakes=[]
        for (y,x),n in np.ndenumerate(matrix):
            if n>0:
                fakes.append((n,(x,y)))
        xys=[]
        ns =[]
        for n,xy in sorted(fakes,key=lambda item:(item[0],-item[1][0],-item[1][1]),reverse=True):
            xys.append('%d,%d'%xy)
            ns .append(n )
        if len(fakes) > 10000:
            print('WARNING: high fake hit rate can cause excessive memory use in plotting - skipping plots!')
            return {'fakerate-%dmasked'%nmask:1.0*sum(ns)/(1<<19)}
        plt.figure()
        plt.subplots_adjust(bottom=0.15)
        plt.title('Fake hits in %d events (strobing for %.3f us, %d pixels masked)'%(nev,sl*0.025,nmask))
        plt.xlabel('Pixel position (x,y)')
        plt.ylabel('Frequency (/event)')
        plt.xticks(range(len(xys)),xys,rotation=45,ha='right')
        if len(xys)>0:
            plt.bar(range(len(xys)),ns,align='center',log=True)
        plt.ylim(0.5/nev,1.0)
        plt.xlim(-1,30)
        #plt.tight_layout()
        #x0,x1,y0,y1=plt.axis()
        #plt.axis((x0,x1,y0,y1+1.25))
        plt.savefig('%s/fakes-sl%03d-nm%03d.png'%(path,sl,nmask))
        plt.close()

        plt.figure()
        plt.title('Fake hit map (%d events, strobing for %.3f us, %d pixels masked)'%(nev,sl*0.025,nmask))
        plt.xlim(0,1024)
        plt.ylim(0,512)
        plt.xticks([0,128,256,384,512,640,768,896,1023])
        plt.yticks([0,128,256,384,511])
        plt.gca().invert_yaxis()
        x=[item[1][0] for item in fakes]
        y=[item[1][1] for item in fakes]
        n=[item[0] for item in fakes]
        plt.scatter(x,y)
        for i,ni in enumerate(n):
            plt.annotate('%d'%(ni*nev),(x[i],y[i]))
        plt.savefig('%s/fakemap-sl%03d-nm%03d.png'%(path,sl,nmask))
        plt.close()
        return {'fakerate-%dmasked'%nmask:1.0*sum(ns)/(1<<19)}

    def analyse(self,path):
        results={}
        try:
          f=open('%s/events.txt'%path)
        except IOError:
            print('ERROR: File {:s}/events.txt could not be read!'.format(path))
            return {}
        matrix=None
        nev=0
        sl=None
        masked=None
        isetting=-1
        for line in f:
            if re.match(r'# STROBE LENGTH (\d+)',line):
                sl=int(re.match(r'# STROBE LENGTH (\d+)',line).group(1))
            elif re.match('# EVENT 1$',line):
                if not matrix is None:
                    results.update(self.analyse_one(path,matrix,nev,sl,masked,isetting))
                matrix=np.zeros((512,1024))
                nev=1
                isetting+=1
            elif re.match('# EVENT',line):
                nev+=1
            elif re.match('# MASKED BAD PIXELS',line):
                pass
            elif re.match('# MASKED NOISY PIXELS',line):
                pass
            else:
                x,y=map(int,line.split())
                matrix[y,x]+=1
        if nev < NEVENTS:
            print('ERROR: File {:s}/events.txt contains less events than expected'.format(path))
            return results
        if matrix is not None:
            results.update(self.analyse_one(path,matrix,nev,sl,masked,isetting))

        return results


