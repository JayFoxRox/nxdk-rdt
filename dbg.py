#!/usr/bin/env python
import socket
import time
import struct
import sys

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
		self._sock.setblocking(1)

	def disconnect(self):
		"""Disconnect from the Xbox"""
		self._sock.close()
		self._sock = None

	def ensure_recv(self, size):
		#FIXME: Block
		data = bytes()
		while size > 0:
			chunk = self._sock.recv(size)
			data = data + chunk
			size -= len(chunk)
		return data

	def info(self):
		"""Get system info"""
		request_buffer = struct.pack("<B", 0)
		print(len(request_buffer))
		self._sock.send(request_buffer)
		response_buffer = self.ensure_recv(4)
		response_data = struct.unpack("<I", response_buffer)
		result = {}
		result['tick_count'] = response_data[0]
		return result

	def debug_print(self, message):
		"""Print a debug string to the screen"""
		message_buffer = message.encode('ascii')
		request_buffer = struct.pack("<BH", 1, len(message_buffer)) + message_buffer
		self._sock.send(request_buffer)

	def reboot(self):
		"""Reboot the system"""
		request_buffer = struct.pack("<B", 2)
		self._sock.send(request_buffer)

	def malloc(self, size):
		"""Allocate memory on the target"""
		request_buffer = struct.pack("<BI", 3, size)
		self._sock.send(request_buffer)
		response_buffer = self.ensure_recv(4)
		response_data = struct.unpack("<I", response_buffer)
		return response_data[0]

	def free(self, address):
		"""Free memory on the target"""
		request_buffer = struct.pack("<BI", 4, address)
		self._sock.send(request_buffer)

	def mem_read(self, address, size):
		"""read memory"""
		request_buffer = struct.pack("<BII", 5, address, size)
		self._sock.send(request_buffer)
		response_buffer = self.ensure_recv(size)
		return response_buffer

	def mem_write(self, address, data):
		"""write memory"""
		request_buffer = struct.pack("<BII", 6, address, len(data)) + data
		self._sock.send(request_buffer)

	def call(self, address, stack=None):
		"""Call a function with given context"""
		if stack is None:
			stack = b''
		request_buffer = struct.pack("<BII", 7, address, len(stack)) + stack
		self._sock.send(request_buffer)
		response_buffer = self.ensure_recv(8*4)
		eax = struct.unpack_from("<I", response_buffer, 7*4)[0]
		return eax

def main():

	if (len(sys.argv) != 2):
		print("Usage: " + sys.argv[0] + " <server>")
		sys.exit(1)

	xbox = Xbox()
	addr = (sys.argv[1], 9269)

	# Connect to the Xbox, display system info
	xbox.connect(addr)
	print(xbox.info())

	# Print something to the screen
	xbox.debug_print("Hello!\n")

	# Allocate, write, read-back, free
	addr = xbox.malloc(1024)
	val = 0x5A
	print("Allocated memory at 0x%x" % addr)
	xbox.mem_write(addr, bytes([val]))
	assert(xbox.mem_read(addr, 1)[0] == val)
	xbox.free(addr)

	# Inject a function which does `rdtsc; ret`.
	# RDTSC means "Read Time Stamp Counter". The Time Stamp Counter is a value,
	# which is incremented every CPU clock cycle.
	code = bytes([0x0F, 0x31, 0xC3])
	addr = xbox.malloc(len(code))
	xbox.mem_write(addr, code)
	rb = xbox.mem_read(addr, 3)
	print("%X %X %X" % (rb[0], rb[1], rb[2]))

	# Repeatedly call the injected function until we have a stable timer
	last_time = None
	print("Testing call using RDTSC (please wait)")
	while True:

		# Ask the Xbox for the RDTSC value
		eax = xbox.call(addr)

		# The timer runs at 733MHz (Xbox CPU Clock speed); Convert to seconds
		current_time = eax / 733333333.33

		# This is necessary as the timer might wrap around between reads:
		# First timestamp would appear to be later than the second timestamp.
		# Also, at startup we only have one measurement, so we can't compare.
		if last_time is not None and current_time > last_time:
			break

		# We wait 1 second (this is the time we expect to measure)
		time.sleep(1.0)
		last_time = current_time

	# Print the measured time (should be ~1.0 seconds) and free function
	print("RDTSC measured %.3f seconds" % (current_time - last_time))
	xbox.free(addr)
	
	repeat_count = 1
	block_size = 2 * 1024 * 1024
	block_pattern = bytes([0xFF]) * block_size
	block_address = xbox.malloc(block_size);

	start_time = time.time()

	for i in range(repeat_count):
		xbox.mem_write(block_address, block_pattern)

		print("%u okay" % i)

	end_time = time.time()
	print("(%u Bytes) / (%f s) to Mbps" % (repeat_count * block_size, end_time - start_time))

	start_time = time.time()

	for i in range(repeat_count):
		block_pattern_check = xbox.mem_read(block_address, block_size)
		#print(block_pattern_check)
		#print(block_pattern)
		#assert(block_pattern_check == block_pattern)

	end_time = time.time()
	print("(%u Bytes) / (%f s) to Mbps" % (repeat_count * block_size, end_time - start_time))

	xbox.free(block_address)
	xbox.debug_print("Okay!")
	
	#xbox.reboot()
	xbox.disconnect()

if __name__ == '__main__':
	main()
