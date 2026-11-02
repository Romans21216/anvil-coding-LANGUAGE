# Anvil Multiplayer Prototype

Anvil currently has an opt-in, Windows-only UDP primitive for a tiny LAN experiment, compiled through the primary generated-C toolchain. It sends one native numeric value at a time and remembers the most recent received value. Run [the host](../examples/network_counter.ANVL), then [the client](../examples/network_client.ANVL).

```anv
netip("0.0.0.0")
nethost(7777)

fn(update)
  net send(var(local-count))
  set var(peer-count) = receive()
end
```

Run `network_counter.ANVL` first, then `network_client.ANVL` on the same machine or LAN. For another machine, change the client's address to the host's LAN IPv4 address. Each side sends its number during `update`; the host learns the first peer address from an incoming datagram and can reply.

Version 2 accepts compact forms `netip("IPv4")`, `nethost(port)`, `nethost(port) --local`, and `netleave()`. `netIP` is also accepted as a spelling of `netip`. Configure a specific local IPv4 address with `netip` before starting a host; without it, the default `0.0.0.0` binds all local interfaces. `--local` forces loopback (`127.0.0.1`) even if another bind address was configured, so only programs on the same machine can reach it. A bind failure reports the source path and line. Binding all interfaces does not configure a firewall, router, or public address; external reachability depends on the machine and network.

The Windows loopback smoke check ran both executables at once: the client increment reached the host, and a host increment reached the client.

## Limits

Packets are unencrypted, unauthenticated, unreliable UDP datagrams containing a platform-native `double`. A received value that is NaN or infinite is rejected by the numeric-expression guard with the `.ANVL` source path and line and exit code 2. Datagrams with a length other than one `double` are ignored. The runtime currently remembers a single peer and does not implement peer limits, matchmaking, reliability, state replication, interpolation, reconnection, or anti-cheat. Use it only for trusted local-network experiments, not public servers or sensitive data. Network calls are opt-in; offline games do not create a socket.

A production multiplayer layer needs a versioned portable packet format, bounded serialization, peer/session lifecycle, validation, rate limits, and a reviewed transport/security design. That work is not represented as complete here.

