#!/usr/bin/env python2

import socket
from dbg_pb2 import *
import time

class XboxError(Exception):
	def __init__(self, msg):
		self.msg = msg

	def __str__(self):
		return self.msg

class Xbox(object):
	def __init__(self):
		self._sock = None

	def connect(self, addr):
		"""Connect to the Xbox"""
		self._sock = socket.create_connection(addr, 5)

	def disconnect(self):
		"""Disconnect from the Xbox"""
		self._sock.close()
		self._sock = None

	def _send_simple_request(self, req):
		"""Send a simple request, expect success"""
		self._sock.send(req.SerializeToString())
		res = Response()
		res.ParseFromString(self._sock.recv(4096))
		if res.type != Response.OK:
			raise XboxError(res.msg)
		return res

	def info(self):
		"""Get system info"""
		req = Request()
		req.type = Request.SYSINFO
		return self._send_simple_request(req).info

	def reboot(self):
		"""Reboot the system"""
		msg = Request()
		msg.type = Request.REBOOT
		self._sock.send(msg.SerializeToString())

	def malloc(self, size):
		"""Allocate memory on the target"""
		req = Request()
		req.type = Request.MALLOC
		req.size = size
		return self._send_simple_request(req).address

	def free(self, addr):
		"""Free memory on the target"""
		req = Request()
		req.type = Request.FREE
		req.address = addr
		return self._send_simple_request(req)

	def mem(self, addr, size=0, data=None):
		"""Read/write system memory"""
		write = data is not None
		req = Request()
		if write:
			req.type = Request.MEM_WRITE
			req.data = data
		else:
			req.type = Request.MEM_READ
			req.size = size
		req.address = addr
		res = self._send_simple_request(req)
		return res if write else res.data

	def debug_print(self, string):
		"""Print a debug string to the screen"""
		req = Request()
		req.type = Request.DEBUG_PRINT
		req.msg = string
		return self._send_simple_request(req)

	def show_debug_screen(self):
		"""Show the debug screen"""
		req = Request()
		req.type = Request.SHOW_DEBUG_SCREEN
		return self._send_simple_request(req)

	def show_front_screen(self):
		"""Show the front screen"""
		req = Request()
		req.type = Request.SHOW_FRONT_SCREEN
		return self._send_simple_request(req)

# FIXME: Remove this one?!
def aligned_alloc(alignment, size):
	address = xbox.malloc(size + alignment)
	align = alignment - (address % alignment)
	return address + (align % alignment)

def ac97_write_u8(address, value):
	xbox.mem(address, bytearray([value]))
def ac97_write_u32(address, value):
	data = bytearray()
	data += [value & 0xFF]
	data += [(value >> 8) & 0xFF]
	data += [(value >> 16) & 0xFF]
	data += [(value >> 24) & 0xFF]
	xbox.mem(address, data)
def ac97_read_u8(address):
	data = xbox.mem(address, size=1)
	return data[0]
def ac97_read_u32(address):
	data = xbox.mem(address, size=4)
	return (data[3] << 24) | (data[2] << 16) | (data[1] << 8) | data[0]


def MmAllocateContiguousMemory(NumberOfBytes, HighestAcceptableAddress):
	aligned_alloc(0x1000, size)
	assert(address <= highest_address)
	return address

pcmDescriptors = 0
spdifDescriptors = 0
nextDescriptor = 0

def XAudioPlay():
	ac97_write_u32(0x118, 0x1d000000) # PCM out - run, allow interrupts
	ac97_write_u32(0x178, 0x1d000000) # SPDIF out - run, allow interrupts

def XAudioPause():
	ac97_write_u32(0x118, 0x1c000000) # PCM out - PAUSE, allow interrupts
	ac97_write_u32(0x178, 0x1c000000) # SPDIF out - PAUSE, allow interrupts

# This is the function you should call when you want to give the
# audio chip some more data.  If you have registered a callback, it
# should call this method.  If you are providing the samples manually,
# you need to make sure you call this function often enough so the

# chip doesn't run out of data
def XAudioProvideSamples(address, length, final = False):
	bufferControl = 0

	if final:
		bufferControl |= 0x4000 # b14=1=last in stream
	bufferControl |= 0x8000 # b15=1=issue IRQ on completion

	#pac97device->pcmOutDescriptor[pac97device->nextDescriptorMod31].bufferStartAddress    = MmGetPhysicalAddress((PVOID)address);
	#pac97device->pcmOutDescriptor[pac97device->nextDescriptorMod31].bufferLengthInSamples = bufferLength / (pac97device->sampleSizeInBits / 8);
	#pac97device->pcmOutDescriptor[pac97device->nextDescriptorMod31].bufferControl         = bufferControl;

	write_u32(pcmDescriptors + nextDescriptor * 8 + 0, address)
	write_u16(pcmDescriptors + nextDescriptor * 8 + 4, length)
	write_u16(pcmDescriptors + nextDescriptor * 8 + 6, bufferControl)
	ac97_write_u8(0x115, nextDescriptor) # set last active PCM descriptor

	#pac97device->pcmSpdifDescriptor[pac97device->nextDescriptorMod31].bufferStartAddress    = MmGetPhysicalAddress((PVOID)address);
	#pac97device->pcmSpdifDescriptor[pac97device->nextDescriptorMod31].bufferLengthInSamples = bufferLength / (pac97device->sampleSizeInBits / 8);
	#pac97device->pcmSpdifDescriptor[pac97device->nextDescriptorMod31].bufferControl         = bufferControl;

	write_u32(spidfDescriptors + nextDescriptor * 8 + 0, address)
	write_u16(spidfDescriptors + nextDescriptor * 8 + 4, length)
	write_u16(spidfDescriptors + nextDescriptor * 8 + 6, bufferControl)
	ac97_write_u8(0x175, nextDescriptor) # set last active SPDIF descriptor

	# increment to the next buffer descriptor (rolling around to 0 once you get to 31)
	nextDescriptor = (nextDescriptor + 1) % 32
}

def write(address, data)
	for i in range(0, len(data)):
		xbox.mem(address + i, data[i]) #FIXME: Transfer DWORD or even full blocks if possible

def XAudioInit():
	#pac97device->mmio = (unsigned int *)0xfec00000;
	#pac97device->nextDescriptorMod31 = 0;
	#pac97device->callback = callback;
	#pac97device->callbackData = data;
	#pac97device->sampleSizeInBits = sampleSizeInBits;
	#pac97device->numChannels = numChannels;

	# initialise descriptors to all 0x00 (no samples)        
	#memset((void *)&pac97device->pcmSpdifDescriptor[0], 0, sizeof(pac97device->pcmSpdifDescriptor));
	#memset((void *)&pac97device->pcmOutDescriptor[0], 0, sizeof(pac97device->pcmOutDescriptor));

	# perform a cold reset
	tmp = ac97_read_u32(0x12C)
	ac97_write_u32(0x12C, tmp | 2)
	
	# wait until the chip is finished resetting...
	while not ac97_read_u32(0x130) & 0x100:
		#FIXME: Wait..
		pass

	# clear all interrupts
	ac97_write_u8(0x116, 0xFF)
	ac97_write_u8(0x176, 0xFF)

	# tell the audio chip where it should look for the descriptors
	#unsigned int pcmAddress = (unsigned int)&pac97device->pcmOutDescriptor[0];
	#unsigned int spdifAddress = (unsigned int)&pac97device->pcmSpdifDescriptor[0];
	pcmDescriptors = MmAllocateContiguousMemory(32 * 8, 0xFFFFFFFF) # Alignment should be 8 [according to openxdk code, BUT I don't want it across 2 pages for safety]
	spdifDescriptors = MmAllocateContiguousMemory(32 * 8, 0xFFFFFFFF) # Alignment should be 8 [according to openxdk code, BUT I don't want it across 2 pages for safety]

	# Clear the descriptors
	write(pcmDescriptors, [0] * 32 * 8)
	write(spdifDescriptors, [0] * 32 * 8)

	ac97_write_u8(0x100, 0) # no PCM input
	ac97_write_u8(0x100, MmGetPhysicalAddress(pcmDescriptors)) # PCM
	ac97_write_u8(0x100, MmGetPhysicalAddress(spdifDescriptors)) # SPDIF

	# default to being silent...
	XAudioPause()
	
	# Register our ISR
	if False:
		vector = HalGetInterruptVector(AUDIO_IRQ, &irql)
		KeInitializeDpc(&DPCObject,&DPC,NULL)
		KeInitializeInterrupt(&InterruptObject, &ISR, NULL, vector, irql, LevelSensitive, FALSE)
		KeConnectInterrupt(&InterruptObject)


def main():
	xbox = Xbox()
	addr = ("127.0.0.1", 8080)
	# addr = ("10.0.1.14", 80)

	# Connect to the Xbox, display system info
	xbox.connect(addr)
	print xbox.info()

	# Print something to the screen
	xbox.debug_print("Hello!")

	# Initialize audio
	XAudioInit()

	# Each buffer is 65534 bytes, we can have up to 32 buffers.. so do this
	while len(samples) > 0:
		max_len = 65534
		if len(samples) > max_len:
			data = samples[0:max_len]
			samples = samples[max_len:]
		else:
			data = samples
			samples = []
		address = MmAllocateContiguousMemory(len(data), 0xFFFFFFFF)
		write(address, data)
		XAudioProvideSamples(address, len(data))
	
	#xbox.reboot()
	xbox.disconnect()

if __name__ == '__main__':
	main()
