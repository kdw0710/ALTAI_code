from chiptests import Test
from probecard import alpide

class BusyViolation(Test):
    def __init__(self):
        super(self.__class__,self).__init__('Busy violation','Test if the busy violation event flag')

    def run(self,pc,path):
        chipid=16
        alpide.init(pc,chipid)
        pc.enable_parallel_port()

        pc.write_alpide_reg(chipid,0,0,1,0x01F9) # Triggered read-out, 20 MHz, clustering: 0x1F9 -> disabled, 0x1FD -> enabled
        pc.write_alpide_reg(chipid,0,0,4,0x0040)
        #pc.write_alpide_reg(chipid,0,0,4,0x0060) # FROMU Configuration Register 1: disable busy monitoring, analog test pulse, enable test strobe
        pc.write_alpide_reg(chipid,0,0,5,    40) # FROMU Configuration Register 2: strobe length
        pc.write_alpide_reg(chipid,0,0,7,     0) # FROMU Pulsing Register 1: delay strobe-pulse
        pc.write_alpide_reg(chipid,0,0,8,  2000) # FROMU Pulsing Register 2: pulse duration
        alpide.reset_readout(pc)
        alpide.set_mask_all(pc,chipid,True)
        pc.send_alpide_opcode(0xE4) # Pixel matrix reset

        of=open('%s/events.txt'%path,'w')
        pc.write_alpide_reg(chipid,0,7,1,0x0200) # force busy
        pc.write_alpide_reg(chipid,0,7,1,0x0600) # disable busy propagation
        ev1=pc.read_parallel_port()[0]
        of.write('# Packet 1 (busy on):\n')
        for b in ev1:
            of.write('%02X\n'%b)
        alpide.trigger(pc)
        ev2=pc.read_parallel_port()[0]
        of.write('# Packet 2 (busy-violation event):\n')
        for b in ev2:
            of.write('%02X\n'%b)
        #pc.write_alpide_reg(chipid,0,7,1,0x0600) # disable busy propagation
        ev3=pc.read_parallel_port()[0]
        of.write('# Packet 3 (busy off):\n')
        for b in ev3:
            of.write('%02X\n'%b)
        alpide.trigger(pc)
        ev4=pc.read_parallel_port()[0]
        of.write('# Packet 4 (normal (empty) event):\n')
        for b in ev4:
            of.write('%02X\n'%b)
        of.close()
        return True

