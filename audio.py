#!/usr/bin/env python3

import sys
import socket
from dbg_pb2 import *
import time
import wave
import struct

xbox = None

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

	def call(self, address, stack, registers=None):
		"""Call a function"""
		req = Request()
		req.type = Request.CALL
		req.address = address
		req.data = stack
		#FIXME: req.registers = registers
		res = self._send_simple_request(req)
		out_registers = {}
		out_registers['eax'] = res.address
		return out_registers

# FIXME: Remove this one?!
def aligned_alloc(alignment, size):
	address = xbox.malloc(size + alignment)
	align = alignment - (address % alignment)
	return address + (align % alignment)

def write(address, data):
	i = 0
	while True:
		remaining = len(data) - i
		#print(str(i) + " / " + str(len(data)))
		if remaining == 0:
			break
		c = min(remaining, 200) # lwip will currently choke on more data [~250 bytes max?]
		xbox.mem(address + i, data=bytes(data[i:i+c]))
		i += c

def read_u8(address):
	data = xbox.mem(address, size=1)
	return int.from_bytes(data, byteorder='little', signed=False)
def read_u16(address):
	data = xbox.mem(address, size=2)
	return int.from_bytes(data, byteorder='little', signed=False)
def read_u32(address):
	data = xbox.mem(address, size=4)
	return int.from_bytes(data, byteorder='little', signed=False)

def write_u8(address, value):
	xbox.mem(address, data=value.to_bytes(1, byteorder='little', signed=False))
def write_u16(address, value):
	xbox.mem(address, data=value.to_bytes(2, byteorder='little', signed=False))
def write_u32(address, value):
	xbox.mem(address, data=value.to_bytes(4, byteorder='little', signed=False))

def ac97_read_u8(address):
	return read_u8(0xFEC00000 + address)
def ac97_read_u16(address):
	return read_u16(0xFEC00000 + address)
def ac97_read_u32(address):
	return read_u32(0xFEC00000 + address)

def ac97_write_u8(address, value):
	write_u8(0xFEC00000 + address, value)
def ac97_write_u16(address, value):
	write_u16(0xFEC00000 + address, value)
def ac97_write_u32(address, value):
	write_u32(0xFEC00000 + address, value)

pcmDescriptors = 0
spdifDescriptors = 0
nextDescriptor = 0

def XAudioPlay():
	#ac97_write_u32(0x118, 0x1D000000) # PCM out - run, allow interrupts
	#ac97_write_u32(0x178, 0x1D000000) # SPDIF out - run, allow interrupts
	ac97_write_u32(0x118, 0x01000000) # PCM out - run
	ac97_write_u32(0x178, 0x01000000) # SPDIF out - run

def XAudioPause():
	#ac97_write_u32(0x118, 0x1C000000) # PCM out - PAUSE, allow interrupts
	#ac97_write_u32(0x178, 0x1C000000) # SPDIF out - PAUSE, allow interrupts
	ac97_write_u32(0x118, 0x00000000) # PCM out - PAUSE
	ac97_write_u32(0x178, 0x00000000) # SPDIF out - PAUSE

# This is the function you should call when you want to give the
# audio chip some more data.  If you have registered a callback, it
# should call this method.  If you are providing the samples manually,
# you need to make sure you call this function often enough so the

# chip doesn't run out of data
def XAudioProvideSamples(address, length, final = False):
	global pcmDescriptors
	global spdifDescriptors
	global nextDescriptor

	bufferControl = 0

	if final:
		bufferControl |= 0x4000 # b14=1=last in stream
	#bufferControl |= 0x8000 # b15=1=issue IRQ on completion

	#pac97device->pcmOutDescriptor[pac97device->nextDescriptorMod31].bufferStartAddress    = MmGetPhysicalAddress((PVOID)address);
	#pac97device->pcmOutDescriptor[pac97device->nextDescriptorMod31].bufferLengthInSamples = bufferLength / (pac97device->sampleSizeInBits / 8);
	#pac97device->pcmOutDescriptor[pac97device->nextDescriptorMod31].bufferControl         = bufferControl;

	write_u32(pcmDescriptors + nextDescriptor * 8 + 0, MmGetPhysicalAddress(address))
	write_u16(pcmDescriptors + nextDescriptor * 8 + 4, length)
	write_u16(pcmDescriptors + nextDescriptor * 8 + 6, bufferControl)
	ac97_write_u8(0x115, nextDescriptor) # set last active PCM descriptor

	#pac97device->pcmSpdifDescriptor[pac97device->nextDescriptorMod31].bufferStartAddress    = MmGetPhysicalAddress((PVOID)address);
	#pac97device->pcmSpdifDescriptor[pac97device->nextDescriptorMod31].bufferLengthInSamples = bufferLength / (pac97device->sampleSizeInBits / 8);
	#pac97device->pcmSpdifDescriptor[pac97device->nextDescriptorMod31].bufferControl         = bufferControl;

	write_u32(spdifDescriptors + nextDescriptor * 8 + 0, MmGetPhysicalAddress(address))
	write_u16(spdifDescriptors + nextDescriptor * 8 + 4, length)
	write_u16(spdifDescriptors + nextDescriptor * 8 + 6, bufferControl)
	ac97_write_u8(0x175, nextDescriptor) # set last active SPDIF descriptor

	# increment to the next buffer descriptor (rolling around to 0 once you get to 31)
	nextDescriptor = (nextDescriptor + 1) % 32

def XAudioInit():
	global pcmDescriptors
	global spdifDescriptors

	# perform a cold reset
	tmp = ac97_read_u32(0x12C)
	ac97_write_u32(0x12C, tmp & 0xFFFFFFFD)
	time.sleep(0.1)
	ac97_write_u32(0x12C, tmp | 2)
	
	# wait until the chip is finished resetting...
	while not ac97_read_u32(0x130) & 0x100:
		#FIXME: Wait..
		print("Waiting")
		pass

	# clear all interrupts
	ac97_write_u8(0x116, 0xFF)
	ac97_write_u8(0x176, 0xFF)

	# tell the audio chip where it should look for the descriptors
	#unsigned int pcmAddress = (unsigned int)&pac97device->pcmOutDescriptor[0];
	#unsigned int spdifAddress = (unsigned int)&pac97device->pcmSpdifDescriptor[0];
	pcmDescriptors = MmAllocateContiguousMemory(32 * 8) # Alignment should be 8 [according to openxdk code, BUT I don't want it across 2 pages for safety]
	spdifDescriptors = MmAllocateContiguousMemory(32 * 8) # Alignment should be 8 [according to openxdk code, BUT I don't want it across 2 pages for safety]

	# Clear the descriptors
	write(pcmDescriptors, [0] * 32 * 8)
	write(spdifDescriptors, [0] * 32 * 8)
	print("PCM desc is v 0x" + format(pcmDescriptors, '08X'))
	print("PCM desc is p 0x" + format(MmGetPhysicalAddress(pcmDescriptors), '08X'))

	ac97_write_u32(0x100, 0) # no PCM input
	ac97_write_u32(0x110, MmGetPhysicalAddress(pcmDescriptors)) # PCM
	ac97_write_u32(0x170, MmGetPhysicalAddress(spdifDescriptors)) # SPDIF

	# default to being silent...
	XAudioPause()
	
	# Register our ISR
	#AUDIO_IRQ = 6
	#irql_address = malloc(1)
	#vector = HalGetInterruptVector(AUDIO_IRQ, irql_address)
	#KeInitializeDpc(&DPCObject,&DPC,NULL)
	#KeInitializeInterrupt(&InterruptObject, &ISR, NULL, vector, read_u8(irql_address), LevelSensitive, FALSE)
	#KeConnectInterrupt(&InterruptObject)

def resolve_export(function):
	#FIXME: If this is a string, look up its ordinal
	image_base = 0x80010000
	TempPtr = read_u32(image_base + 0x3C);
	TempPtr = read_u32(image_base + TempPtr + 0x78);
	ExportCount = read_u32(image_base + TempPtr + 0x14);
	ExportBase = image_base + read_u32(image_base + TempPtr + 0x1C);
	#FIXME: Read all exports at once and parse them locally
	
	#for i in range(0, ExportCount):
	#	ordinal = i + 1
	#	print("@" + str(ordinal) + ": 0x" + format(image_base + read_u32(ExportBase + i * 4), '08X'))

	index = (function - 1) # Ordinal

	return image_base + read_u32(ExportBase + index * 4)

def MmAllocateContiguousMemory(NumberOfBytes):
	return call_stdcall(165, "<I", NumberOfBytes)

def MmGetPhysicalAddress(BaseAddress):
	return call_stdcall(173, "<I", BaseAddress)

def call_stdcall(function, types, *arguments):
	address = resolve_export(function)
	registers = xbox.call(address, struct.pack(types, *arguments))
	return registers['eax']

def main():
	global xbox

	xbox = Xbox()
	addr = (sys.argv[1], 9269)

	wav = wave.open(sys.argv[2], 'rb')
	print(wav.getframerate())
	assert(wav.getnchannels() == 2)
	assert(wav.getsampwidth() == 2)
	assert(wav.getframerate() == 48000)

	# Connect to the Xbox, display system info
	xbox.connect(addr)
	print(xbox.info())

	# Resolve some export
#	if True:
		#resolve_export(1)
#		addr = MmAllocateContiguousMemory(0x1000)
#		print("Got 0x" + format(addr, '08X'))

	def ac97_status():
		print("CIV=0x" + format(ac97_read_u8(0x114), '02X'))
		print("LVI=0x" + format(ac97_read_u8(0x115), '02X'))
		print("SR=0x" + format(ac97_read_u16(0x116), '04X'))
		print("pos=0x" + format(ac97_read_u16(0x118), '04X'))
		print("piv=0x" + format(ac97_read_u16(0x11A), '04X'))
		print("CR=0x" + format(ac97_read_u8(0x11B), '02X'))
		print("global control=0x" + format(ac97_read_u32(0x12C), '08X'))
		print("global status=0x" + format(ac97_read_u32(0x130), '08X'))
		def dump_buffers(addr):
			descriptor = 0x80000000 | ac97_read_u32(addr)
			print("??? desc is p 0x" + format(descriptor, '08X'))
			# FIXME: Download all descriptors in one packet and then parse here
			for i in range(0, 32):
				addr = read_u32(descriptor + i * 8 + 0)
				length = read_u16(descriptor + i * 8 + 4)
				control = read_u16(descriptor + i * 8 + 6)
				print(str(i) + ": 0x" + format(addr, '08X') + " (" + str(length) + " samples); control: 0x" + format(control, '04X'))
		dump_buffers(0x110)
		dump_buffers(0x170)

		#ac97_write_u32(0x110, MmGetPhysicalAddress(pcmDescriptors)) # PCM
		#ac97_write_u32(0x170, MmGetPhysicalAddress(spdifDescriptors)) # SPDIF

	#ac97_status()
	#ac97_write_u16(0x02, 0xFFFF) # Front volume [not working?!]
	#ac97_write_u16(0x18, 0xFFFF) # PCM volume [not working?!]
	#print("vol?=0x" + format(ac97_read_u16(0x18), '04X'))
	#print("vol?=0x" + format(ac97_read_u16(0x02), '04X'))

	# Audio test	
	if True:

		# Print something to the screen
		xbox.debug_print("Audio init!")

		ac97_status()

		# Initialize audio
		XAudioInit()

		xbox.debug_print("Audio load!")

		# Don't use more than 32 buffers.. or you will overwrite the beginning
		while True:
			data = wav.readframes(0xFFFF // 2)
			if len(data) == 0:
				break
			address = MmAllocateContiguousMemory(len(data))
			print("Allocated " + str(len(data)) + " bytes")
			write(address, data)
			XAudioProvideSamples(address, len(data) // 2)
			print("next buffer")

		xbox.debug_print("Audio play!")

		XAudioPlay()

		xbox.debug_print("Audio end!")

		ac97_status()
	
	#xbox.reboot()
	xbox.disconnect()

if __name__ == '__main__':
	main()
