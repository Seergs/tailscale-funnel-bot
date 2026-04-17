# tailscale-funnel-bot

A telegram bot that temporarily exposes Kubernetes services to the internet using [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel)

## How it works

Send `/expose namespace/service` and the bot creates a Tailscale Funnel ingress, notifies you when the URL is ready, and automatically closes it after 1 hour (configurable)

## Commands

| Command | Description |
|---|---|
| `/expose namespace/service [duration]` | Expose a service via Tailscale Funnel. Duration examples: `30m`, `2h` (default: 1h). Notifies you when the URL is ready |
| `/close namespace/service` | Immediately close the funnel for a service |
| `/status` | List all active funnels with time remaining before auto-close |
| `/list` | List all available services; active funnels are marked with 🟢 |

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

## Configuration

All configuration is via environment variables, set in `deploy/secret.yaml`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_TOKEN` | Yes | — | Telegram bot token |
| `ALLOWED_USER_ID` | Yes | — | Your Telegram user ID |
| `FUNNEL_DURATION_SECONDS` | No | `3600` | Auto-close timeout in seconds |
| `IGNORED_NAMESPACES` | No | `kube-system,tailscale,funnel-bot,flux-system,longhorn-system` | Namespaces hidden from `/list` |
| `IGNORED_SERVICES` | No | — | Comma-separated service names to always hide from `/list` |
| `ALLOWED_SERVICES` | No | — | Comma-separated service names to always show in `/list`, bypassing namespace filters |
| `LOG_FORMAT` | No | `json` | Log output format: `json` for structured logging, `text` for human-readable output |

## Security considerations

> Tailscale Funnel exposes your service to the public internet. Only expose services
> that are protected with authentication, and close funnels as soon as you no longer need them

- Only the configured `ALLOWED_USER_ID` can interact with the bot
- The bot requires cluster-wide read access to Services and write access to Ingresses. Please review `deploy/rbac.yaml` before deploying
- Funnels are automatically closed after `FUNNEL_DURATION_SECONDS` to limit exposure

## License

MIT
