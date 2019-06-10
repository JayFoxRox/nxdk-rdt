XBE_TITLE = AAAAAAA
GEN_XISO = $(XBE_TITLE).iso
SRCS = $(CURDIR)/main.c $(CURDIR)/net.c $(CURDIR)/dbgd.c
NXDK_NET = y

include $(NXDK_DIR)/Makefile
