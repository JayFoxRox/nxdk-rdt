#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#include <hal/input.h>
#include <hal/xbox.h>
#include <hal/xbox.h>

#include <xboxrt/debug.h>

#include <xboxkrnl/xboxkrnl.h>

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

static int dbgd_sysinfo(int fd);
static int dbgd_debug_print(int fd);
static int dbgd_reboot(int fd);
static int dbgd_malloc(int fd);
static int dbgd_free(int fd);
static int dbgd_mem_read(int fd);
static int dbgd_mem_write(int fd);
static int dbgd_call(int fd);

//FIXME: This order must always be kept consistent!

typedef int (*dbgd_req_handler)(int fd);
static dbgd_req_handler handlers[] = {
    &dbgd_sysinfo,     // 0
    &dbgd_debug_print, // 1
    &dbgd_reboot,      // 2
    &dbgd_malloc,      // 3
    &dbgd_free,        // 4
    &dbgd_mem_read,    // 5
    &dbgd_mem_write,   // 6
    &dbgd_call         // 7
};

static bool ensure_recv(int fd, void* data, size_t length) {

    // Loop until all data is read
    debugPrint("Reading %u\n", length);
    uint8_t* cursor = data;
    while(length > 0) {

        int ret = recv(fd, cursor, length, 0);
        debugPrint("  - chunk %u / %u\n", ret, length);

        // Check for errors
        if (ret == -1) {
            return false;
        }

        // Check for end of stream
        if (ret == 0) {
            return false;
        }

        // Advance in buffer
        assert((ret > 0) && (ret <= length));
        cursor += ret;
        length -= ret;
    }

    return true;
}

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
        bool success = ensure_recv(fd, &command_type, 1);  
        if (!success) {
          debugPrint("Unable to receive command\n");
          break;
        }

        /* Handle the command */
        debugPrint("Received command %u\n", command_type);
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
        debugPrint("Waiting for accept\n");
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
    bool success;

    typedef struct {
      uint32_t size;
    } RequestData;

    RequestData request;
    success = ensure_recv(fd, &request, sizeof(request));
    assert(success);

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
    bool success;

    typedef struct {
      uint32_t address;
    } RequestData;

    RequestData request;
    success = ensure_recv(fd, &request, sizeof(request));
    assert(success);

    free((void*)request.address);

    return 0;
}

static int dbgd_mem_read(int fd)
{
    bool success;

    typedef struct {
      uint32_t address;
      uint32_t size;
    } RequestData;

    typedef struct {
      uint8_t data[1];
    } ResponseData;

    RequestData request;
    success = ensure_recv(fd, &request, sizeof(request));

    size_t response_data_length = sizeof(ResponseData) - 1 + request.size;
    ResponseData* response_data = malloc(response_data_length);

    unsigned int i = 0;
    unsigned int s = request.size;

    while(s >= 4) {
      *(uint32_t*)&response_data->data[i] = *(volatile uint32_t*)(request.address + i);
      i += 4;
      s -= 4;
    }
    while(s >= 2) {
      *(uint16_t*)&response_data->data[i] = *(volatile uint16_t*)(request.address + i);
      i += 2;
      s -= 2;
    }
    while(s >= 1) {
      *(uint8_t*)&response_data->data[i] = *(volatile uint8_t*)(request.address + i);
      i += 1;
      s -= 1;
    }

    debugPrint("Responding %u / %u / %u bytes\n", sizeof(ResponseData), response_data_length, request.size);
    send(fd, response_data, response_data_length, 0);

    free(response_data);

    return 0;
}

static int dbgd_mem_write(int fd)
{
    bool success;

    typedef struct {
      uint32_t address;
      uint32_t data_length;
    } RequestHeader;

    typedef struct {
      uint8_t data[1];
    } RequestData;

    RequestHeader request_header;
    success = ensure_recv(fd, &request_header, sizeof(request_header));
    assert(success);

    assert(request_header.data_length > 0);
    size_t request_data_length = sizeof(RequestData) - 1 +
                                 request_header.data_length;
    RequestData* request_data = malloc(request_data_length);
    success = ensure_recv(fd, request_data, request_data_length);
    assert(success);

    unsigned int i = 0;
    unsigned int s = request_header.data_length;

    while(s >= 4) {
      *(volatile uint32_t*)(request_header.address + i) = *(uint32_t*)&request_data->data[i];
      i += 4;
      s -= 4;
    }
    while(s >= 2) {
      *(volatile uint16_t*)(request_header.address + i) = *(uint16_t*)&request_data->data[i];
      i += 2;
      s -= 2;
    }
    while(s >= 1) {
      *(volatile uint8_t*)(request_header.address + i) = *(uint8_t*)&request_data->data[i];
      i += 1;
      s -= 1;
    }

    free(request_data);

    return 0;
}

static int dbgd_debug_print(int fd)
{
    bool success;

    typedef struct {
      uint16_t length;
    } RequestHeader;

    typedef struct {
      char message[1];
    } RequestData;

    RequestHeader request_header;
    success = ensure_recv(fd, &request_header, sizeof(request_header));
    assert(success);

    assert(request_header.length > 0);
    size_t request_data_length = sizeof(RequestData) - 1 +
                                 request_header.length;
    RequestData* request_data = malloc(request_data_length);
    success = ensure_recv(fd, request_data, request_data_length);
    assert(success);

    debugPrint("%.*s", request_header.length, request_data->message);

    free(request_data);

    return 0;
}

static int dbgd_call(int fd)
{
    bool success;

    typedef struct {
      uint32_t address;
      uint32_t stack_length;
    } RequestHeader;

    typedef struct {
      uint8_t stack[1];
    } RequestData;

    typedef struct {
      uint8_t stack[8*4];
    } ResponseData;

    RequestHeader request_header;
    success = ensure_recv(fd, &request_header, sizeof(request_header));
    assert(success);

    size_t request_data_length = 0;
    RequestData* request_data = NULL;
    if (request_header.stack_length > 0) {
      request_data_length = sizeof(RequestData) - 1 +
                            request_header.stack_length;
      request_data = malloc(request_data_length);
      success = ensure_recv(fd, request_data, request_data_length);
      assert(success);
    }

    ResponseData response_data;

    // These variables will be used as parameters for inline assembly.
    // We make them static as the stack pointer will be changed.
    // So we want to address them globally.
    static uint32_t stack_pointer;
    static uint32_t stack_backup;
    static uint32_t address;

    // Allocate a stack for working and space for supplied data
    size_t stack_size = 0x1000 + request_header.stack_length;
    uint8_t* stack_data = malloc(stack_size);

    // Push optional stack contents, starting at top of stack
    stack_pointer = (uint32_t)&stack_data[stack_size];
    if (request_header.stack_length > 0) {
      stack_pointer -= request_header.stack_length;
      memcpy((void*)stack_pointer, request_data->stack, request_header.stack_length);
    }

    // We can already free our request data
    if (request_data != NULL) {
      free(request_data);
    }

    // Set address to call
    address = request_header.address;

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

    // Copy pusha data into return buffer
    stack_pointer -= sizeof(response_data.stack);
    memcpy(response_data.stack, (void*)stack_pointer, sizeof(response_data.stack));

    free(stack_data);

    send(fd, &response_data, sizeof(response_data), 0);

    return 0;
}
