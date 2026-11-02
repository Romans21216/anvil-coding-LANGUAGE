#define WIN32_LEAN_AND_MEAN
#include "anvil_runtime.h"

#include <string.h>

#pragma comment(lib, "Ws2_32.lib")

static SOCKET anvil_net_socket = INVALID_SOCKET;
static SOCKADDR_IN anvil_net_peer;
static int anvil_net_has_peer;
static int anvil_winsock_started;
static double anvil_net_value;

static int anvil_net_ready(void) {
  if (anvil_winsock_started)
    return 1;
  WSADATA data;
  if (WSAStartup(MAKEWORD(2, 2), &data) != 0)
    return 0;
  anvil_winsock_started = 1;
  return 1;
}
static unsigned long anvil_net_bind_ip;
int anvil_net_set_ip(const char *address) {
  struct in_addr parsed;
  if (!anvil_net_ready() || !address || inet_pton(AF_INET, address, &parsed) != 1)
    return 0;
  anvil_net_bind_ip = parsed.s_addr;
  return 1;
}
int anvil_net_host(int port) { return anvil_net_host_at(port, 0); }
int anvil_net_host_at(int port, int local_only) {
  if (!anvil_net_ready())
    return 0;
  if (anvil_net_socket != INVALID_SOCKET)
    closesocket(anvil_net_socket);
  anvil_net_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (anvil_net_socket == INVALID_SOCKET)
    return 0;
  SOCKADDR_IN local;
  memset(&local, 0, sizeof(local));
  local.sin_family = AF_INET;
  local.sin_addr.s_addr = local_only ? htonl(INADDR_LOOPBACK) : anvil_net_bind_ip;
  local.sin_port = htons((u_short)port);
  u_long nonblocking = 1;
  if (ioctlsocket(anvil_net_socket, FIONBIO, &nonblocking) != 0) {
    closesocket(anvil_net_socket); anvil_net_socket = INVALID_SOCKET; return 0;
  }
  anvil_net_has_peer = 0;
  if (bind(anvil_net_socket, (SOCKADDR *)&local, sizeof(local)) != 0) {
    closesocket(anvil_net_socket); anvil_net_socket = INVALID_SOCKET; return 0;
  }
  return 1;
}
int anvil_net_join(const char *address, int port) {
  if (!anvil_net_ready())
    return 0;
  if (anvil_net_socket != INVALID_SOCKET)
    closesocket(anvil_net_socket);
  anvil_net_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (anvil_net_socket == INVALID_SOCKET)
    return 0;
  memset(&anvil_net_peer, 0, sizeof(anvil_net_peer));
  anvil_net_peer.sin_family = AF_INET;
  anvil_net_peer.sin_port = htons((u_short)port);
  if (inet_pton(AF_INET, address, &anvil_net_peer.sin_addr) != 1) {
    closesocket(anvil_net_socket);
    anvil_net_socket = INVALID_SOCKET;
    return 0;
  }
  u_long nonblocking = 1;
  if (ioctlsocket(anvil_net_socket, FIONBIO, &nonblocking) != 0) {
    closesocket(anvil_net_socket);
    anvil_net_socket = INVALID_SOCKET;
    return 0;
  }
  anvil_net_has_peer = 1;
  return 1;
}
double anvil_net_receive(void) {
  if (anvil_net_socket == INVALID_SOCKET)
    return anvil_net_value;
  double value;
  SOCKADDR_IN from;
  int from_len = sizeof(from);
  int count = recvfrom(anvil_net_socket, (char *)&value, (int)sizeof(value), 0,
                       (SOCKADDR *)&from, &from_len);
  if (count == (int)sizeof(value)) {
    anvil_net_value = value;
    if (!anvil_net_has_peer) {
      anvil_net_peer = from;
      anvil_net_has_peer = 1;
    }
  }
  return anvil_net_value;
}
void anvil_net_send(double value) {
  if (anvil_net_socket == INVALID_SOCKET || !anvil_net_has_peer)
    return;
  (void)sendto(anvil_net_socket, (const char *)&value, (int)sizeof(value), 0,
               (SOCKADDR *)&anvil_net_peer, sizeof(anvil_net_peer));
}
void anvil_net_close(void) {
  if (anvil_net_socket != INVALID_SOCKET) {
    closesocket(anvil_net_socket);
    anvil_net_socket = INVALID_SOCKET;
  }
  if (anvil_winsock_started) {
    WSACleanup();
    anvil_winsock_started = 0;
  }
  anvil_net_has_peer = 0;
}
