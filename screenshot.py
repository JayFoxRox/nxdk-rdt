#!/usr/bin/env python3

import sys
import socket
from dbg_pb2 import *
import time
import wave
import struct
from PIL import Image

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

def read(address, size):
	i = 0
	data = bytes()
	while True:
		remaining = size - i
		if remaining == 0:
			break
		c = min(remaining, 100) # lwip will currently choke on more data [~250 bytes max?]
		data += xbox.mem(address + i, size=c)
		i += c
	return data

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

def IoDeviceObjectType():
	return resolve_export(70)

def IoSynchronousDeviceIoControlRequest(IoControlCode, DeviceObject, InputBuffer, InputBufferLength, OutputBuffer, OutputBufferLength, ReturnedOutputBufferLength, InternalDeviceIoControl):
	#IN ULONG IoControlCode,
	#IN PDEVICE_OBJECT DeviceObject,
	#IN PVOID InputBuffer OPTIONAL,
	#IN ULONG InputBufferLength,
	#OUT PVOID OutputBuffer OPTIONAL,
	#IN ULONG OutputBufferLength,
	#OUT PULONG ReturnedOutputBufferLength OPTIONAL,
	#IN BOOLEAN InternalDeviceIoControl) # FIXME: How to handle this one properly? xxxB? Bxxx? I?
	return call_stdcall(84, "<IIIIIIII", IoControlCode, DeviceObject, InputBuffer, InputBufferLength, OutputBuffer, OutputBufferLength, ReturnedOutputBufferLength, InternalDeviceIoControl)

def MmAllocateContiguousMemory(NumberOfBytes):
	return call_stdcall(165, "<I", NumberOfBytes)

def MmGetPhysicalAddress(BaseAddress):
	return call_stdcall(173, "<I", BaseAddress)

def ObReferenceObjectByName(ObjectName, Attributes, ObjectType, ParseContext, Object):
#IN POBJECT_STRING ObjectName,
#	IN ULONG Attributes,
#	IN POBJECT_TYPE ObjectType,
#	IN OUT PVOID ParseContext OPTIONAL,
#OUT PVOID *Object
	return call_stdcall(247, "<IIIII", ObjectName, Attributes, ObjectType, ParseContext, Object)

def RtlInitAnsiString(DestinationString, SourceString):
#IN OUT PANSI_STRING DestinationString,
#IN PCSZ SourceString
	return call_stdcall(289, "<II", DestinationString, SourceString)

def call_stdcall(function, types, *arguments):
	address = resolve_export(function)
	registers = xbox.call(address, struct.pack(types, *arguments))
	return registers['eax']

SCSI_IOCTL_DATA_OUT         = 0
SCSI_IOCTL_DATA_IN          = 1
SCSI_IOCTL_DATA_UNSPECIFIED = 2

IOCTL_SCSI_PASS_THROUGH        = 0x4D004
IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014

NULL = 0

FALSE = 0x00000001
TRUE  = 0x00000001 # FIXME: Check if these are correct!

def strdup(string):
	addr = xbox.malloc(len(string) + 1)
	xbox.mem(addr, data=bytes(string + '\x00', encoding='ascii'))
	return addr


def get_dvd_device_object():
	#static PDEVICE_OBJECT device = NULL;
	#if (device == NULL):
	#ANSI_STRING cdrom

	ANSI_STRING_len = 8
	cdrom_addr = xbox.malloc(ANSI_STRING_len)

	string = strdup("\\Device\\Cdrom0")
	RtlInitAnsiString(cdrom_addr, string)
	xbox.free(string)

	#// Get a reference to the dvd object so that we can query it for info.
	device_ptr_addr = xbox.malloc(4) # Pointer to device
	status = ObReferenceObjectByName(cdrom_addr, 0, IoDeviceObjectType(), NULL, device_ptr_addr)
	device_ptr = read_u32(device_ptr_addr)
	xbox.free(device_ptr_addr)

	xbox.free(cdrom_addr)

	print("Status: 0x" + format(status, '08X'))
	print("Device: 0x" + format(device_ptr, '08X'))

	if (status != 0):
		return NULL

	assert(device_ptr != NULL)
	return device_ptr

def main():
	global xbox

	xbox = Xbox()
	addr = (sys.argv[1], 9269)

	# Connect to the Xbox, display system info
	xbox.connect(addr)
	print(xbox.info())

	base = 0xFD000000
	def crtc_read(i):
		write_u8(base + 0x6013D4, i)
		return read_u8(base + 0x6013D5)
	pitch = crtc_read(0x13)
	pitch |= (crtc_read(0x19) & 0xE0) << 3
	pitch |= (crtc_read(0x25) & 0x20) << 6
	pitch *= 8
	bytes_per_pixel = crtc_read(0x28) & 0x7F #FIXME: 3 when it's actually 4..
	is_565 = False if bytes_per_pixel != 2 else (read_u32(base + 0x680600) & 0x1000) > 0
	framebuffer_addr = 0x80000000 | read_u32(base + 0x600800)
	print("fb: " + format(framebuffer_addr, '08X'))
	print("pitch: " + str(pitch))
	print("565: " + str(is_565))
	print("bytes_per_pixel: " + str(bytes_per_pixel))

	# Stolen from QEMU:
	if False: #  if (s->vbe_regs[VBE_DISPI_INDEX_ENABLE] & VBE_DISPI_ENABLED) {
		#      width = s->vbe_regs[VBE_DISPI_INDEX_XRES];
		#      height = s->vbe_regs[VBE_DISPI_INDEX_YRES];
		assert(False)
	else:
		VGA_CRTC_H_DISP     = 1
		VGA_CRTC_OVERFLOW   = 7
		VGA_CRTC_V_DISP_END = 0x12
		width = (crtc_read(VGA_CRTC_H_DISP) + 1) * 8
		height = crtc_read(VGA_CRTC_V_DISP_END)
		height |= (crtc_read(VGA_CRTC_OVERFLOW) & 0x02) << 7
		height |= (crtc_read(VGA_CRTC_OVERFLOW) & 0x40) << 3
		height += 1;

	print(str(width) + " x " + str(height))

	framebuffer_data = read(framebuffer_addr, pitch * height)

	screenshot = Image.new('RGB', (width, height))
	pixels = screenshot.load()
	for y in range (0,height):
		for x in range (0,width):
			if bytes_per_pixel == 3:
				p = y * pitch + x * 4
				b = framebuffer_data[p + 0]
				g = framebuffer_data[p + 1]
				r = framebuffer_data[p + 2]
				a = framebuffer_data[p + 3]
			else:
				p = y * pitch + x * 2
				if is_565:
					#FIXME: Untested!
					b = framebuffer_data[p + 0] & 0x1F
					g = (framebuffer_data[p + 0] >> 5) & 0x7
					g |= framebuffer_data[p + 1] & 0x7
					r = (framebuffer_data[p + 1] >> 3) & 0x1F
					#FIXME: Bring to [0, 255] range?!
					a = 0

					b = int(r / 0x1F * 0xFF)
					g = int(g / 0x1F * 0xFF)
					r = int(b / 0x1F * 0xFF)
					# alpha is zero anyway, needs no rescaling

				else:
					#FIXME: Untested!
					b = framebuffer_data[p + 0] & 0x1F
					g = (framebuffer_data[p + 0] >> 5) & 0x7
					g |= framebuffer_data[p + 1] & 0x3
					r = (framebuffer_data[p + 1] >> 2) & 0x1F
					a = (framebuffer_data[p + 1] >> 7) & 0x1

					b = int(r / 0x1F * 0xFF)
					g = int(g / 0x3F * 0xFF)
					r = int(b / 0x1F * 0xFF)
					a = int(a / 0x1 * 0xFF)

			pixels[x, y]=(r,g,b)

	screenshot.save("screenshot.png")

	#xbox.reboot()
	xbox.disconnect()

if __name__ == '__main__':
	main()
