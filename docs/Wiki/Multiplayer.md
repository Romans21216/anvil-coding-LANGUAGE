# Multiplayer Prototype

Anvil currently provides a Windows UDP prototype for exchanging one number with one LAN peer:

```anv
net host(7777)

fn(update)
  net send(var(score))
  set var(peer-score) = receive()
end
```

The host remembers the first peer that sends a datagram. The client uses `net join("127.0.0.1", 7777)`. See the runnable samples in `examples/network_counter.ANVL` and `examples/network_client.ANVL`.

This transport is unreliable and unencrypted, uses a platform-native `double`, and does not implement multiple peers, versioned serialization, validation, sessions, replication, prediction, rate limits, or authentication. Keep it to trusted LAN experiments. Do not use it for public Internet game servers.

