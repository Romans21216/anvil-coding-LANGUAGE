#define WIN32_LEAN_AND_MEAN
#include "anvil_runtime.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

#pragma comment(lib, "Ws2_32.lib")

static SOCKET anvil_net_socket = INVALID_SOCKET;
static SOCKADDR_IN anvil_net_peer;
static int anvil_net_has_peer;
static int anvil_winsock_started;
static double anvil_net_value;
static double anvil_net_packet_value;
static uint32_t anvil_net_packet_message_id = UINT32_MAX;
static uint32_t anvil_net_packet_send_sequence;
static uint32_t anvil_net_packet_receive_sequence;
static int anvil_net_packet_received;
static int anvil_net_packet_sequence_received;

enum { ANVIL_NET_PACKET_SIZE = 24 };

static void anvil_net_write_u32(unsigned char *out, uint32_t value) {
  out[0] = (unsigned char)(value >> 24);
  out[1] = (unsigned char)(value >> 16);
  out[2] = (unsigned char)(value >> 8);
  out[3] = (unsigned char)value;
}

static uint32_t anvil_net_read_u32(const unsigned char *in) {
  return ((uint32_t)in[0] << 24) | ((uint32_t)in[1] << 16) |
         ((uint32_t)in[2] << 8) | (uint32_t)in[3];
}

static int anvil_net_same_peer(const SOCKADDR_IN *left,
                               const SOCKADDR_IN *right) {
  return left->sin_family == right->sin_family &&
         left->sin_port == right->sin_port &&
         left->sin_addr.s_addr == right->sin_addr.s_addr;
}

static int anvil_net_sequence_is_newer(uint32_t candidate, uint32_t current) {
  uint32_t distance = candidate - current;
  return distance != 0 && distance < UINT32_C(0x80000000);
}

static void anvil_net_reset_packet_state(void) {
  anvil_net_packet_value = 0.0;
  anvil_net_packet_message_id = UINT32_MAX;
  anvil_net_packet_send_sequence = 0;
  anvil_net_packet_receive_sequence = 0;
  anvil_net_packet_received = 0;
  anvil_net_packet_sequence_received = 0;
}

static void anvil_net_write_f64(unsigned char *out, double value) {
  uint64_t bits;
  memcpy(&bits, &value, sizeof(bits));
  for (unsigned int i = 0; i < 8; ++i)
    out[i] = (unsigned char)(bits >> (56 - 8 * i));
}

static double anvil_net_read_f64(const unsigned char *in) {
  uint64_t bits = 0;
  for (unsigned int i = 0; i < 8; ++i)
    bits = (bits << 8) | in[i];
  double value;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

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
  anvil_net_reset_packet_state();
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
  anvil_net_reset_packet_state();
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

/* Version 1 packet layout: magic[4], version, payload type, reserved[2],
   sequence[4], message id[4], and one IEEE-754 binary64 payload[8]. All
   integer fields and the floating-point bit pattern use network byte order. */
double anvil_net_packet_send(double message_id, double value) {
  if (!isfinite(message_id) || message_id < 0.0 ||
      message_id > 4294967295.0 || floor(message_id) != message_id ||
      !isfinite(value) || anvil_net_socket == INVALID_SOCKET ||
      !anvil_net_has_peer)
    return 0.0;
  unsigned char packet[ANVIL_NET_PACKET_SIZE] = {
      'A', 'N', 'V', 'P', 1, 1, 0, 0};
  ++anvil_net_packet_send_sequence;
  if (anvil_net_packet_send_sequence == 0)
    ++anvil_net_packet_send_sequence;
  anvil_net_write_u32(packet + 8, anvil_net_packet_send_sequence);
  anvil_net_write_u32(packet + 12, (uint32_t)message_id);
  anvil_net_write_f64(packet + 16, value);
  int sent = sendto(anvil_net_socket, (const char *)packet,
                    (int)sizeof(packet), 0,
                    (SOCKADDR *)&anvil_net_peer, sizeof(anvil_net_peer));
  return sent == (int)sizeof(packet) ? 1.0 : 0.0;
}

double anvil_net_packet_receive(void) {
  if (anvil_net_socket == INVALID_SOCKET)
    return anvil_net_packet_value;
  unsigned char packet[ANVIL_NET_PACKET_SIZE + 1];
  SOCKADDR_IN from;
  int from_len = sizeof(from);
  int count = recvfrom(anvil_net_socket, (char *)packet, sizeof(packet), 0,
                       (SOCKADDR *)&from, &from_len);
  if (count != ANVIL_NET_PACKET_SIZE || memcmp(packet, "ANVP", 4) != 0 ||
      packet[4] != 1 || packet[5] != 1 || packet[6] != 0 || packet[7] != 0)
    return anvil_net_packet_value;
  uint32_t sequence = anvil_net_read_u32(packet + 8);
  double value = anvil_net_read_f64(packet + 16);
  if (sequence == 0 || !isfinite(value) ||
      (anvil_net_has_peer && !anvil_net_same_peer(&from, &anvil_net_peer)) ||
      (anvil_net_packet_sequence_received &&
       !anvil_net_sequence_is_newer(sequence,
                                    anvil_net_packet_receive_sequence)))
    return anvil_net_packet_value;
  anvil_net_packet_receive_sequence = sequence;
  anvil_net_packet_sequence_received = 1;
  anvil_net_packet_message_id = anvil_net_read_u32(packet + 12);
  anvil_net_packet_value = value;
  anvil_net_packet_received = 1;
  if (!anvil_net_has_peer) {
    anvil_net_peer = from;
    anvil_net_has_peer = 1;
  }
  return anvil_net_packet_value;
}

double anvil_net_packet_id(void) {
  return anvil_net_packet_received ? (double)anvil_net_packet_message_id : -1.0;
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
  anvil_net_reset_packet_state();
}
