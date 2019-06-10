Xbox Remote Dev Tool
====================

This tool will allow you remote control of an original Xbox from your development system over the network.

This tool is actively being developed and maintained.
New features and improvements are welcome.

For the list of supported commands, check the command handlers in dbgd.c.
An example client, written in Python, is provided in dbg.py.


Test With XQEMU
---------------
Run with
#FIXME: Update ports!
		-net nic,model=nvnet -net user,hostfwd=tcp::8080-10.0.2.15:80 \

Then connect to 127.0.0.1:8080.


Run on a real Xbox
------------------
Build using nxdk, then copy the XBE over to your xbox.
