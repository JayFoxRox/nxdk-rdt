#!/bin/env python3

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

	def mem(self, addr, value=None):
		"""Read/write system memory"""
		write = value is not None
		req = Request()
		req.type    = Request.MEM_WRITE if write else Request.MEM_READ
		req.address = addr
		req.size    = 1 # TODO: Support word, dword, qword accesses
		if write:
			req.value = value
		res = self._send_simple_request(req)
		return res if write else res.value

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

	def scsi_dvd(self, command, _buffer=None, size=0):
		"""Send an SCSI command to the DVD drive"""
		req = Request()
		req.command = command
		if _buffer:
			#FIXME: Assert that size is 0?
			req.type = Request.SCSI_DVD_OUT
			req.buffer = _buffer
		else:
			req.type = Request.SCSI_DVD_IN
			req.size = size
		res = self._send_simple_request(req)
		return res if _buffer else res.buffer

def main():
	xbox = Xbox()
	#addr = ("127.0.0.1", 8080)
	addr = ("192.168.177.2", 80)
	# addr = ("10.0.1.14", 80)

	# Connect to the Xbox, display system info
	xbox.connect(addr)
	print(xbox.info())

	#print(xbox.scsi_dvd(bytes([0x12,0x00,0x00,0x00,36+100,0x00]), size=36 + 100)) # INQUIRY [Does not work for my drive?!]

	def mode_sense():
		#FIXME: Make a more generic mode_sense
		action = 0
		code = 0x3E
		# req_b = bytes([0x5A, 0x00, (action << 6) | (code & 0x3F), 0x00, 0x00, 0x00, 0x00, (length >> 8) & 0xFF, length & 0xFF, 0x00])
		# print(' 0x'.join(format(x, '02x') for x in req_b))


	# Get mode page
	length = (20+8) # Length of auth page + mode sense header
	req_b = bytes([0x5A, 0x00, 0x3E, 0x00, 0x00, 0x00, 0x00, (length >> 8) & 0xFF, length & 0xFF, 0x00])
	#print(' 0x'.join(format(x, '02x') for x in req_b))
	res_b = xbox.scsi_dvd(req_b, size=length)
	#print(' 0x'.join(format(x, '02x') for x in res_b))

	def read8(b):
		return b.pop(0)

	def read32(b):
		x0 = read8(b)
		x1 = read8(b)
		x2 = read8(b)
		x3 = read8(b)
		return (x3 << 24) | (x2 << 16) | (x1 << 8) | x0

	res = list(res_b)

	# Pop off the MODE_SENSE header
	read8(res)
	read8(res)
	read8(res)
	read8(res)
	read8(res)
	read8(res)
	read8(res)
	read8(res)

	print(res)

	d = {}
	#d['wtfthisshouldbehere'] = read8(res) # No idea what this is?!

	d['mode_page'] = read8(res)
	d['length'] = read8(res) #	Excluding this & the field before. Should always be 18
	d['partition_select'] = read8(res) # 0x00 = Video partition
	                                   # 0x01 = Xbox partition
	                                   #
	                                   # This will be set to 0x01 by the kernel when the last challenge was verified. This is done by sending the same challenge again, the challenge id / value is not reset.
	d['unknown0'] = read8(res) # If this is not 1, the kernel will reject this as an XGD (but still allow normal access?![citation needed])
	d['authenticated'] = read8(res) # 0x00 = Not authenticated
	                                # 0x01 = Already authenticated | authentication in progress
	                                #
	                                # This will be set to 0x01 by the kernel when the first challenge is send.
	tmp = read8(res)
	d['booktype'] = (tmp >> 4) & 0xF # Booktype 0xD is used for Xbox games. This must match info from the SS.
	d['bookversion'] = tmp & 0xF
	d['unknown1'] = read8(res) # ?
	d['challenge_id'] = read8(res)
	d['challenge_value'] = read32(res)
	d['response_value'] = read32(res)
	d['unknown2'] = read8(res) #Unused?
	d['unknown3'] = read8(res) #Unused?
	d['unknown4'] = read8(res) # Unused?
	d['unknown5'] = read8(res) # Unused?

	print(d)


	# Mode select

	length = (20+8) # Length of auth page + mode select header
	# Somehow xbox uses a mode sense 10 like-structure but uses mode select 10 ?
	req_b = bytes([0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, (length >> 8) & 0xFF, length & 0xFF, 0x00])
	#header_b = bytes([0, 0x1A, 0, 0, 0, 0, 0, 0])
	header_b = bytes([0, 0x00, 0, 0, 0, 0, 0, 0])
#	data_b = bytes([0x3E, 18, 0, 1, 1, 0xD1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]) # Authenticate and select video partition
#	data_b = bytes([0x3E, 18, 1, 1, 1, 0xD1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]) # Authenticate and select xbox partition
	
	#print(' 0x'.join(format(x, '02x') for x in req_b))
	res_b = xbox.scsi_dvd(req_b, header_b + data_b)



	length = 254 # Must be even + can't be larger than 255 because of NXDK / etherforce / lwip fuckup
	#print(xbox.scsi_dvd(bytes([0xad, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, (length >> 8) & 0xFF, length & 0xFF, 0x00, 0xc0]), size=length)) # Get PFI
	#print(xbox.scsi_dvd(bytes([0xad, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, (length >> 8) & 0xFF, length & 0xFF, 0x00, 0xc0]), size=length)) # Get DMI
	#print(xbox.scsi_dvd(bytes([0xad, 0x00, 0xff, 0x02, 0xfd, 0xff, 0xfe, 0x00, (length >> 8) & 0xFF, length & 0xFF, 0x00, 0xc0]), size=length)) # Get SS
	#                            ad                                                                   << Operation (Read DVD Structure)
	#                                  00                                                             << Media Type & such
	#                                        ff    02    fd    ff                                     << Block
	#                                                                fe                               << Layer
	#                                                                      00                         << Format code (Physical descriptor)
	#                                                                            06    64             << Length (0x664 = 1636)
	#                                                                                        00       << AGID etc.
	#                                                                                              c0 << Control [Vendor specific]

#	print(xbox.scsi_dvd(bytes([0x12,0x00,0x00,0x08,0x00,0xC0]), bytes([]))) # No idea.. my philips drive won't respect any message anyway


	# Allocate, write, read-back, free
	#addr = xbox.malloc(1024)
	#val = 0x5A
	#print("Allocated memory at 0x%x" % addr)
	#xbox.mem(addr, val)
	#assert(xbox.mem(addr) == val)
	#xbox.free(addr)
	
	xbox.disconnect()

if __name__ == '__main__':
	main()
