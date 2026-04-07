import os

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_ID: int = int(os.environ["ALLOWED_USER_ID"])

FUNNEL_DURATION_SECONDS: int = int(os.getenv("FUNNEL_DURATION_SECONDS", "3600"))

ANNOTATION_FUNNEL = "tailscale.com/funnel"
ANNOTATION_EXPOSED_AT = "tailscale-funnel-bot/exposed-at"

_DEFAULT_IGNORED = "kube-system,tailscale,funnel-bot,flux-system,longhorn-system"

IGNORED_NAMESPACES: frozenset[str] = frozenset(
    ns.strip()
    for ns in os.getenv("IGNORED_NAMESPACES", _DEFAULT_IGNORED).split(",")
    if ns.strip()
)
