#ifndef SCSI_H
#define SCSI_H

#include <xboxkrnl/xboxkrnl.h>

#define SCSI_IOCTL_DATA_OUT          	0
#define SCSI_IOCTL_DATA_IN           	1
#define SCSI_IOCTL_DATA_UNSPECIFIED		2

#define IOCTL_SCSI_PASS_THROUGH 		    0x4D004
#define IOCTL_SCSI_PASS_THROUGH_DIRECT	0x4D014

NTSTATUS scsi_command(UCHAR data_in, const void* command, size_t command_length, const void* buffer, size_t buffer_length);

#endif
