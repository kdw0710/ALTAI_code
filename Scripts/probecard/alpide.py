import time
import logging

def set_mask_all(pc,chipid,mask=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,mask<<1|0<<0)        # set data and select mask register
    pc.write_alpide_reg(chipid,0,4,0x87,0xFFFF)           # select all
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
def set_mask_row(pc,chipid,row,mask=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,mask<<1|0<<0)        # set data and select mask register 
    pc.write_alpide_reg(chipid,0,4,0x83,0xFFFF)           # select all columns
    pc.write_alpide_reg(chipid,row>>4,4,0x4,1<<(row&0xF)) # select one row
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
def set_mask_col(pc,chipid,col,mask=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,mask<<1|0<<0)        # set data and select mask register 
    pc.write_alpide_reg(chipid,col>>5&0x1F,4,0x1+(col>>4&0x1),1<<(col&0xF)) # select one column
    pc.write_alpide_reg(chipid,0,4,0x84,0xFFFF)           # select all rows
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
def set_mask_xy(pc,chipid,x,y,mask=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,mask<<1|0<<0)        # set data and select mask register 
    pc.write_alpide_reg(chipid,x>>5&0x1F,4,0x1+(x>>4&0x1),1<<(x&0xF)) # select one column
    pc.write_alpide_reg(chipid,y>>4,4,0x4,1<<(y&0xF))     # select one row
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all

def set_pulsing_all(pc,chipid,enable=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,enable<<1|1<<0)      # set data and select pulse register
    pc.write_alpide_reg(chipid,0,4,0x87,0xFFFF)           # select all
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
def set_pulsing_row(pc,chipid,row,enable=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,enable<<1|1<<0)      # set data and select pulse register
    pc.write_alpide_reg(chipid,0,4,0x83,0xFFFF)           # select all columns
    pc.write_alpide_reg(chipid,row>>4,4,0x4,1<<(row&0xF)) # select one row
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
def set_pulsing_col(pc,chipid,col,enable=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,enable<<1|1<<0)      # set data and select pulse register
    pc.write_alpide_reg(chipid,col>>5&0x1F,4,0x1+(col>>4&0x1),1<<(col&0xF)) # select one column
    pc.write_alpide_reg(chipid,0,4,0x84,0xFFFF)           # select all rows
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
def set_pulsing_xy(pc,chipid,x,y,enable=True):
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all
    pc.write_alpide_reg(chipid,0,5,0,enable<<1|1<<0)      # set data and select pulse register
    pc.write_alpide_reg(chipid,x>>5&0x1F,4,0x1+(x>>4&0x1),1<<(x&0xF)) # select one column
    pc.write_alpide_reg(chipid,y>>4,4,0x4,1<<(y&0xF))     # select one row
    pc.write_alpide_reg(chipid,0,4,0x87,0)                # deselect all

def global_reset(pc):
    pc.send_alpide_opcode(0xD2)

def reset_readout(pc):
    pc.send_alpide_opcode(0x63)

def trigger(pc):
    pc.send_alpide_opcode(0x55)

def reset_matrix(pc):
    pc.send_alpide_opcode(0xE4)

def pulse(pc):
    pc.send_alpide_opcode(0x78)

def decode_event(data,chipid):
    i=0
    length=len(data)
    log_warn  = logging.getLogger().isEnabledFor(logging.WARNING)
    log_debug = logging.getLogger().isEnabledFor(logging.DEBUG)

    # skip leading idles
    while i<length and (data[i]==0xFF or data[i]==0xF1 or data[i]==0xF0 or data[i]==0x00): # FIXME: why 00
        i+=1
    hits=[]
    if   data[i]&0xF0==0xE0: # chip empty frame
        assert i+1<length
        if log_debug:
            logging.debug('data[%d]=%02X (empty event)'%(i,data[i]))
        assert data[0]&0x0F==chipid&0x0F
        bc=data[i+1]>>3
        sc=data[i+1]&0x3
        i+=2
        flags=0x00 # not available in empty frame...
    elif data[i]&0xF0==0xA0: # chip header
        if data[0]&0x0F!=chipid&0x0F:
          logging.error("ERROR in CHIPID (4LSB). Status %X but chip id should be %X"%(data[0], chipid))
        assert data[0]&0x0F==chipid&0x0F
        assert i+4<length
        if log_debug:
            logging.debug('data[%d:%d]=%02X-%02X (chip header)'%(i,i+1,data[i],data[i+1]))
        bc=data[i+1]>>3
        sc=data[i+1]&0x3
        i+=2
        reg=-1
        last=-1
        assert data[i]&0xE0==0xC0
        while i<length:
            if data[i]&0xE0==0xC0: # region header
                if log_debug:
                    logging.debug('data[%d]=%02X (region header)'%(i,data[i]))
                reg=data[i]&0x1F
                i+=1
            elif data[i]&0xC0==0x40: # data short
                assert i+1<length
                if log_debug:
                    logging.debug('data[%d:%d]=%02X-%02X (data short)'%(i,i+1,data[i],data[i+1]))
                d=reg<<14|(data[i]&0x3F)<<8|data[i+1]
                if log_warn and not last<d:
                    l = len(hits)
                    logging.warning('priority error: (addresses[%d]=%04X)>=(addresses[%d]=%04X)'%(l-1,last,l,d))
                last = d
                hits.append((d>>9&0x3FE|(d^d>>1)&0x1,d>>1&0x1FF))
                i+=2
            elif data[i]&0xC0==0x00: # data long
                assert i+2<length
                if log_debug:
                    logging.debug('data[%d:%d]=%02X-%02X-%02X (data long)'%(i,i+2,data[i],data[i+1],data[i+2]))
                d=reg<<14|(data[i]&0x3F)<<8|data[i+1]
                if log_warn and not last<d:
                    l = len(hits)
                    logging.warning('priority error: (addresses[%d]=%04X)>=(addresses[%d]=%04X)'%(l-1,last,l,d))
                last = d
                hits.append((d>>9&0x3FE|(d^d>>1)&0x1,d>>1&0x1FF))
                for j in range(7):
                    if data[i+2]>>j&1==1:
                        h = d+j+1
                        if log_warn and not last<h:
                            l = len(hits)
                            logging.warning('priority error: (addresses[%d]=%04X)>=(addresses[%d]=%04X)'%(l-1,last,l,h))
                        last = h
                        hits.append((h>>9&0x3FE|(h^h>>1)&0x1,h>>1&0x1FF))
                i+=3
            elif data[i]&0xF0==0xB0: # chip trailer
                if log_debug:
                    logging.debug('data[%d]=%02X (chip trailer)'%(i,data[i]))
                flags=data[i]&0x0F
                break
            elif data[i]==0xFF: # IDLE
                if log_debug:
                    logging.debug('data[%d]=%02X (IDLE)'%(i,data[i]))
                i+=1
            elif data[i]==0xF0: # BUSY OFF
                if log_debug:
                    logging.debug('data[%d]=%02X (BUSY OFF)'%(i,data[i]))
                i+=1
            elif data[i]==0xF1: # BUSY ON
                if log_debug:
                    logging.debug('data[%d]=%02X (BUSY ON)'%(i,data[i]))
                i+=1
            else:
                assert False
        assert data[i]&0xF0==0xB0 # chip trailer found
        i+=1
    else:
        logging.warning('bad first word of event: %02X'%data[i])
        assert False
    if log_warn:
        while i<length:
            if data[i]!=0xFF and data[i]!=0x00:
                logging.warning('unexpected trailing byte: data[%d]=%02X'%(i,data[i]))
                assert data[i]==0xFF or data[i]==0x00 # ?!?
            i+=1
    return (bc,sc,flags,hits)

def init(pc,chipid,bb=False,vbb=-6.0):
    pc.enable_por(False)
    pc.set_chipid(chipid)
    time.sleep(0.2)
    pc.power_on(bb=bb,vbb=vbb)
    time.sleep(0.2)
    global_reset(pc)
    time.sleep(0.1)
    pc.write_alpide_reg(chipid,0,0,16,0x0070|chipid&0xF)
    reset_matrix(pc)
    reset_readout(pc)

