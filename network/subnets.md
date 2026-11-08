# Subnet Allocation

The address block is `10.20.0.0/16`. Subnets are allocated from the largest host requirement to the smallest, beginning at `10.20.0.0`. For each requirement, the smallest subnet satisfying `2^(32 - prefix) - 2 >= required hosts` is used.

| Subnet | Hosts needed | Calculation | Network/prefix | Usable host range | Broadcast | Usable hosts |
|---|---:|---|---|---|---|---:|
| app | 1,000 | `2^10 - 2 = 1,022` | `10.20.0.0/22` | `10.20.0.1` - `10.20.3.254` | `10.20.3.255` | 1,022 |
| public | 250 | `2^8 - 2 = 254` | `10.20.4.0/24` | `10.20.4.1` - `10.20.4.254` | `10.20.4.255` | 254 |
| data | 100 | `2^7 - 2 = 126` | `10.20.5.0/25` | `10.20.5.1` - `10.20.5.126` | `10.20.5.127` | 126 |
| management | 20 | `2^5 - 2 = 30` | `10.20.5.128/27` | `10.20.5.129` - `10.20.5.158` | `10.20.5.159` | 30 |

## Working

- The app subnet needs 1,000 usable addresses. Ten host bits provide 1,022 usable addresses, so its prefix is `/22`.
- The next unused aligned network is `10.20.4.0`. The public subnet needs 250 usable addresses; eight host bits provide 254, giving `/24`.
- The next network is `10.20.5.0`. The data subnet needs 100 usable addresses; seven host bits provide 126, giving `/25`.
- The next network is `10.20.5.128`. The management subnet needs 20 usable addresses; five host bits provide 30, giving `/27`.

## Why reply rules and rule order matter

A network ACL is stateless: it evaluates every packet independently and does not remember that an earlier packet established a connection. Therefore, the public subnet needs explicit rules for inbound replies from the app subnet and outbound replies to clients on ephemeral destination ports `1024-65535`. Without those reverse-direction rules, valid response packets would be denied by the default-deny behaviour.

Rules are evaluated in ascending rule-number order and the first match decides the packet. The deny rule for `198.51.100.0/24` therefore has a lower number than the general HTTP and HTTPS allow rules. If the web allows came first, traffic from the abusive range would match them before reaching the deny rule.

