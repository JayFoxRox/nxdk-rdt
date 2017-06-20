NXDK_DIR = $(CURDIR)/../nxdk
NXDK_NET = y

XBE_TITLE = nxdk-rdt
GEN_XISO = $(XBE_TITLE).iso
SRCS = $(wildcard $(CURDIR)/*.c)
SHADER_OBJS = ps.inl vs.inl

SRCS += $(CURDIR)/lib/protobuf-c/protobuf-c.c

CFLAGS += -I$(CURDIR)
CFLAGS += -I$(CURDIR)/lib

include $(NXDK_DIR)/Makefile

.PHONY:clean-local
clean-local: clean
	rm -f *.inl* log.txt dump.cap main.lib

%_pb2.py: %.proto
	protoc --python_out=$(CURDIR)/ $(notdir $<)

%.pb-c.c %.pb-c.h: %.proto
	protoc-c --c_out=$(CURDIR)/ $(notdir $<)
