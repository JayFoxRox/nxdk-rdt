#include <xboxkrnl/xboxkrnl.h>

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

NTSTATUS scsi_dvd_command(UCHAR data_in, const void* command, size_t command_length, const void* buffer, size_t buffer_length)
{
    PDEVICE_OBJECT device = get_dvd_device_object();
    assert(device != NULL);

    SCSI_PASS_THROUGH_DIRECT pass_through;
    RtlZeroMemory(&pass_through, sizeof(SCSI_PASS_THROUGH_DIRECT));

    pass_through.Length = sizeof(SCSI_PASS_THROUGH_DIRECT);
    pass_through.DataIn = data_in;
    pass_through.DataBuffer = buffer;
    pass_through.DataTransferLength = buffer_length;

    assert(command_length <= sizeof(pass_through.Cdb));
    memcpy(&pass_through.Cdb, command, command_length);

    NTSTATUS status = IoSynchronousDeviceIoControlRequest(IOCTL_SCSI_PASS_THROUGH_DIRECT,
                          device, &pass_through, sizeof(SCSI_PASS_THROUGH_DIRECT),
                          NULL, 0, NULL, FALSE);

    return status;
}

