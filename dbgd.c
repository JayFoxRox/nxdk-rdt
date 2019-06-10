#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#include <hal/input.h>
#include <hal/xbox.h>
#include <hal/xbox.h>

#include <xboxrt/debug.h>

#include <xboxkrnl/xboxkrnl.h>

#include <pbkit/pbkit.h>

#include <lwip/api.h>
#include <lwip/arch.h>
#include <lwip/debug.h>
#include <lwip/dhcp.h>
#include <lwip/init.h>
#include <lwip/netif.h>
#include <lwip/opt.h>
#include <lwip/sys.h>
#include <lwip/tcpip.h>
#include <lwip/timers.h>
#include <netif/etharp.h>

#include <pktdrv.h>

#include <lwip/sockets.h>

#include "net.h"
#include "dbgd.h"

#define DBGD_PORT 9269

#ifndef HTTPD_DEBUG
#define HTTPD_DEBUG LWIP_DBG_OFF
#endif

#define ARRAY_SIZE(x) (sizeof(x) / sizeof(x[0]))

static void* get_transfer_buffer(uint32_t size) {
    static uint32_t buffer_size = 0;
    static void* buffer = NULL;

    if (size > buffer_size) {
        if (buffer != NULL) {
            free(buffer);
        }
        buffer = malloc(size);
        buffer_size = size;
    }
    return buffer;
}

typedef int Dbg__Request;
typedef int Dbg__Response;

static int dbgd_sysinfo(int fd);
static int dbgd_reboot(int fd);
static int dbgd_malloc(int fd);
static int dbgd_free(int fd);
static int dbgd_mem_read(Dbg__Request *req, Dbg__Response *res);
static int dbgd_mem_write(Dbg__Request *req, Dbg__Response *res);
static int dbgd_debug_print(int fd);
static int dbgd_call(Dbg__Request *req, Dbg__Response *res);

//FIXME: This order must always be kept consistent!

typedef int (*dbgd_req_handler)(int fd);
static dbgd_req_handler handlers[] = {
    &dbgd_sysinfo,
    &dbgd_reboot,
    &dbgd_malloc,
    &dbgd_free,
//    &dbgd_mem_read,
//    &dbgd_mem_write,
    &dbgd_debug_print,
//    &dbgd_call
};

static void dbgd_serve(int fd, struct sockaddr address)
{
    char socket_address[INET_ADDRSTRLEN];
    //FIXME: Add variant for IPv6
    struct sockaddr_in *ip = (struct sockaddr_in *)&address;
    inet_ntop(AF_INET, &(ip->sin_addr), socket_address, INET_ADDRSTRLEN);

    debugPrint("[%s connected]\n", socket_address);

    while (1) {

        /* Read header */
        uint8_t command_type;
        recv(fd, &command_type, 1, 0);

        /* Handle the command */
        assert(command_type < ARRAY_SIZE(handlers));
        handlers[command_type](fd);

    }

    /* Close the connection */
    close(fd);

    debugPrint("[%s disconnected]\n", socket_address);
}

static void dbgd_thread(void *arg)
{
    int ret;
    LWIP_UNUSED_ARG(arg);

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        debugPrint("Error when trying to create socket\n");
        return;
    }

    struct sockaddr_in address;
    memset(&address, 0x00, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(DBGD_PORT);
 
    /* Now bind the host address using bind() call.*/
    ret = bind(fd, (struct sockaddr *)&address, sizeof(address));
    if (ret < 0) {
        debugPrint("Error when trying to bind\n");
        return;
    }

    listen(fd,5);
    
    while(true) {
        struct sockaddr client_address;
        socklen_t client_address_len;
        int client_fd = accept(fd, &client_address, &client_address_len);

        if (client_fd == -1) {
            debugPrint("Error in accept()\n");
            break;
        }

        debugPrint("Accepted\n");
        dbgd_serve(client_fd, client_address);
    }

    close(fd);
}

void dbgd_init(void)
{
    sys_thread_new("dbgd",
                   dbgd_thread,
                   NULL,
                   DEFAULT_THREAD_STACKSIZE,
                   DEFAULT_THREAD_PRIO);
}

static int dbgd_sysinfo(int fd)
{
    typedef struct {
      uint32_t tick_count;
    } ResponseData;

    ResponseData response;
    response.tick_count = XGetTickCount();

    send(fd, &response, sizeof(response), 0);

    return 0;
}

static int dbgd_reboot(int fd)
{
    XReboot();
    asm volatile ("jmp .");

    return 0;
}

static int dbgd_malloc(int fd)
{
    typedef struct {
      uint32_t size;
    } RequestData;

    RequestData request;
    recv(fd, &request, sizeof(request), 0);

    typedef struct {
      uint32_t address;
    } ResponseData;

    ResponseData response;
    response.address = (uint32_t)malloc(request.size);

    send(fd, &response, sizeof(response), 0);

    return 0;
}

static int dbgd_free(int fd)
{
    typedef struct {
      uint32_t address;
    } RequestData;

    RequestData request;
    recv(fd, &request, sizeof(request), 0);

    free((void*)request.address);

    return 0;
}

#if 0
static int dbgd_mem_read(Dbg__Request *req, Dbg__Response *res)
{
    if (!req->has_address || !req->has_size)
        return DBG__RESPONSE__TYPE__ERROR_INCOMPLETE_REQUEST;

    res->address = req->address;
    res->has_address = 1;

    res->data.len  = req->size;
    res->data.data = get_transfer_buffer(res->data.len);
    res->has_data = 1;

    unsigned int i = 0;
    unsigned int s = req->size;

    while(s >= 4) {
      *(uint32_t*)&res->data.data[i] = *(volatile uint32_t*)(req->address + i);
      i += 4;
      s -= 4;
    }
    while(s >= 2) {
      *(uint16_t*)&res->data.data[i] = *(volatile uint16_t*)(req->address + i);
      i += 2;
      s -= 2;
    }
    while(s >= 1) {
      *(uint8_t*)&res->data.data[i] = *(volatile uint8_t*)(req->address + i);
      i += 1;
      s -= 1;
    }

    return 0;
}

static int dbgd_mem_write(Dbg__Request *req, Dbg__Response *res)
{
    if (!req->has_address || !req->has_data)
        return DBG__RESPONSE__TYPE__ERROR_INCOMPLETE_REQUEST;

    unsigned int i = 0;
    unsigned int s = req->data.len;

    while(s >= 4) {
      *(volatile uint32_t*)(req->address + i) = *(uint32_t*)&req->data.data[i];
      i += 4;
      s -= 4;
    }
    while(s >= 2) {
      *(volatile uint16_t*)(req->address + i) = *(uint16_t*)&req->data.data[i];
      i += 2;
      s -= 2;
    }
    while(s >= 1) {
      *(volatile uint8_t*)(req->address + i) = *(uint8_t*)&req->data.data[i];
      i += 1;
      s -= 1;
    }

    return 0;
}
#endif

static int dbgd_debug_print(int fd)
{
    typedef struct {
      uint16_t length;
    } RequestHeader;

    typedef struct {
      char message[];
    } RequestData;

    RequestHeader request_header;
    recv(fd, &request_header, sizeof(request_header), 0);

    assert(request_header.length > 0);
    size_t request_data_length = sizeof(RequestData) + request_header.length + 1;
    RequestData* request_data = malloc(request_data_length);
    recv(fd, request_data, request_data_length, 0);

    // Zero-terminate message
    request_data->message[request_data_length - 1] = '\0';

    debugPrint("%s", request_data->message);

    free(request_data);

    return 0;
}

#if 0

static int dbgd_call(Dbg__Request *req, Dbg__Response *res)
{
    if (!req->has_address)
        return DBG__RESPONSE__TYPE__ERROR_INCOMPLETE_REQUEST;

    // These variables will be used as parameters for inline assembly.
    // We make them static as the stack pointer will be changed.
    // So we want to address them globally.
    static uint32_t stack_pointer;
    static uint32_t stack_backup;
    static uint32_t address;

    // Allocate a stack for working and space for supplied data
    size_t stack_size = 0x1000;
    if (req->has_data) {
      stack_size += req->data.len;
    }
    uint8_t* stack_data = malloc(stack_size);

    // Push optional stack contents, starting at top of stack
    stack_pointer = (uint32_t)&stack_data[stack_size];
    if (req->has_data) {
      stack_pointer -= req->data.len;
      memcpy((void*)stack_pointer, req->data.data, req->data.len);
    }

    // Set address to call
    address = req->address;

    asm("pusha\n"
        "mov %%esp, %[stack_backup]\n"     // Keep copy of original stack
        "mov %[stack_pointer], %%esp\n"
        "call *%[address]\n"               // Call the function
        "mov %[stack_pointer], %%esp\n"    // push all register values to stack
        "pusha\n"
        "mov %[stack_backup], %%esp\n"     // Recover original stack
        "popa\n"

        : // No outputs
        : [stack_pointer] "m" (stack_pointer),
          [stack_backup]  "m" (stack_backup),
          [address]       "m" (address)
        : "memory");

    // Get transfer buffer for a set of registers from pusha
    res->data.len  = 32;
    res->data.data = get_transfer_buffer(res->data.len);
    res->has_data = 1;

    // Copy pusha data into return buffer
    stack_pointer -= res->data.len;
    memcpy(res->data.data, (void*)stack_pointer, res->data.len);

    free(stack_data);

    return 0;
}
#endif
