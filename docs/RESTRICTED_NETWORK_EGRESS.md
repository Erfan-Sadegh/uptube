# Restricted-Network Egress

Use this setup only for a server that cannot reach Google, YouTube, or AvalAI
directly. It keeps SSH and the host route independent from the VPN. Only
explicitly connected application containers use the egress proxy.

## Server Layout

The server-local Gluetun stack lives outside this repository:

```text
/opt/mioondar-proxy/
  docker-compose.yml
  wireguard/
    wg0.conf
```

`wg0.conf` contains credentials. Keep it owned by `root:root` with mode `600`.
Never commit it, print it in logs, or send it through chat.

The Gluetun stack creates the external Docker network `mioondar-egress`.
`docker-compose.egress.yml` connects only `backend` and `worker` to that
network and configures `http://gluetun:8888` as their HTTP(S) proxy.

The host-bound proxy ports stay local:

```text
127.0.0.1:8888  Gluetun HTTP proxy
127.0.0.1:9950  SOCKS5 proxy
```

Do not bind either port to `0.0.0.0`. The SOCKS5 service does not use
authentication and must not become a public proxy.

## WireGuard Compatibility

Use an IPv4 interface address and IPv4 default route in the mounted
`wg0.conf`. Gluetun rejects an IPv6 WireGuard interface address in this setup.

The tested server-local Gluetun settings are:

```yaml
image: qmcgaw/gluetun:v3.41.1
environment:
  WIREGUARD_MTU: "1280"
  WIREGUARD_PERSISTENT_KEEPALIVE_INTERVAL: "25s"
  DNS_UPSTREAM_RESOLVER_TYPE: plain
  DNS_UPSTREAM_PLAIN_ADDRESSES: "8.8.8.8:53,8.8.4.4:53"
```

Plain DNS is acceptable here because application DNS queries still travel
inside the encrypted WireGuard tunnel before reaching the resolver. Prefer DoH
when the VPN provider carries it reliably.

## Health Checks

```bash
cd /opt/mioondar-proxy
sudo docker compose ps
sudo docker inspect --format '{{.State.Health.Status}}' gluetun
curl --proxy http://127.0.0.1:8888 https://api.ipify.org
curl --socks5-hostname 127.0.0.1:9950 https://api.ipify.org
curl -I --proxy http://127.0.0.1:8888 https://www.youtube.com
ss -ltnp | grep -E ':8888|:9950'
```

The expected listener addresses are `127.0.0.1`, not `0.0.0.0`.

Before production use, run repeated checks. A single successful request is not
enough:

```bash
for i in $(seq 1 10); do
  curl --fail --proxy http://127.0.0.1:8888 \
    --connect-timeout 5 --max-time 15 https://www.youtube.com >/dev/null \
    && echo ok || echo failed
  sleep 4
done
```

Do not deploy the application until all or nearly all checks pass. A recent
WireGuard handshake only proves that the endpoint is reachable; it does not
prove that the provider's outbound transit is stable.

## Operations

```bash
cd /opt/mioondar-proxy
sudo docker compose up -d --pull never
sudo docker compose restart
sudo docker compose logs --tail 120 gluetun
```

The server uses Docker registry mirrors. If a direct Docker Hub pull falls
back to blocked public infrastructure, pull explicitly through the mirror and
tag the image locally:

```bash
sudo docker pull mirror-docker.runflare.com/qmcgaw/gluetun:v3.41.1
sudo docker tag mirror-docker.runflare.com/qmcgaw/gluetun:v3.41.1 qmcgaw/gluetun:v3.41.1
```

## References

- [Gluetun custom provider setup](https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/custom.md)
- [Gluetun health-check troubleshooting](https://github.com/qdm12/gluetun-wiki/blob/main/faq/healthcheck.md)
