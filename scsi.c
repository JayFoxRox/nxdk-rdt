#include <xboxkrnl/xboxkrnl.h>
#include <xboxrt/debug.h>
#include <string.h>
#include <assert.h>

#include "scsi.h"

static PDEVICE_OBJECT get_dvd_device_object(void)
{
    static PDEVICE_OBJECT device = NULL;

    if (device == NULL) {
	      ANSI_STRING cdrom;  
        RtlInitAnsiString(&cdrom, "\\Device\\Cdrom0");

        // Get a reference to the dvd object so that we can query it for info.
        NTSTATUS status = ObReferenceObjectByName(&cdrom, 0, &IoDeviceObjectType, NULL, (void**)&device);

	      if (!NT_SUCCESS(status)) {
            return NULL;
        }

        assert(device != NULL);
    }

    return device;
}

NTSTATUS scsi_dvd_command(UCHAR data_in, const void* command, size_t command_length, void* buffer, size_t buffer_length)
{
    PDEVICE_OBJECT device = get_dvd_device_object();
    assert(device != NULL);
//debugPrint("device: %d\n", device);
//debugPrint("size: %d\n", sizeof(SCSI_PASS_THROUGH_DIRECT));

    SCSI_PASS_THROUGH_DIRECT pass_through;
    memset(&pass_through, 0x00, sizeof(SCSI_PASS_THROUGH_DIRECT));

    pass_through.Length = sizeof(SCSI_PASS_THROUGH_DIRECT);
    pass_through.DataIn = data_in;
    pass_through.DataBuffer = (PVOID)buffer;
    pass_through.DataTransferLength = buffer_length;

    assert(command_length <= sizeof(pass_through.Cdb));
    memcpy(pass_through.Cdb, command, command_length);
    //pass_through.CdbLength = command_length;

//for(int i = 0; i < command_length; i++) {
//  debugPrint("%d\n", pass_through.Cdb[i]);
//}

    NTSTATUS status = IoSynchronousDeviceIoControlRequest(IOCTL_SCSI_PASS_THROUGH_DIRECT,
                          device, &pass_through, sizeof(pass_through),
                          NULL, 0, /* &output_length */ NULL, FALSE);

debugPrint("status: %d\n", status);

    return status;
}

