# tailscale-funnel-bot

A telegram bot that temporarily exposes Kubernetes services to the internet using [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel)

## How it works

Send `/expose namespace/service` and the bot creates a Tailscale Funnel ingress, notifies you when the URL is ready, and automatically closes it after 1 hour (configurable)

## Prerequisites

- Kubernetes cluster with [Tailscale Operator](https://tailscale.com/docs/features/kubernetes-operator) installed
- A Telegram bot token from [@BotFather](https://t.me/botfather)
- Your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))

## Deploy

**1. Create the secret**

```bash
cp deploy/secret.example.yaml deploy/secret.yaml
```

Edit `deploy/secret.yaml` and fill in your `TELEGRAM_TOKEN` and `ALLOWED_USER_ID`

**2. Apply**

```bash
kubectl apply -f deploy/secret.yaml
kubectl apply -k deploy/
```

**3. Verify**

```bash
kubectl rollout status deployment/tailscale-funnel-bot -n funnel-bot
```

## Commands

All configuration is via environment vairbales, set in `deploy/secret.yaml`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_TOKEN` | Yes | — | Telegram bot token |
| `ALLOWED_USER_ID` | Yes | — | Your Telegram user ID |
| `FUNNEL_DURATION_SECONDS` | No | `3600` | Auto-close timeout in seconds |
| `IGNORED_NAMESPACES` | No | `kube-system,tailscale,funnel-bot,flux-system,longhorn-system` | Namespaces hidden from `/list` |

## Security considerations

- Only the configured `ALLOWED_USER_ID` can interact with the bot
- The bot requires cluster-wide read access to Services and write access to Ingresses. Please review `deploy/rbac.yaml` before deploying
- Funnels are automatically closed after `FUNNEL_DURATION_SECONDS` to limit exposure

## License

MIT
