import os

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_ID: int = int(os.environ["ALLOWED_USER_ID"])

FUNNEL_DURATION_SECONDS: int = int(os.getenv("FUNNEL_DURATION_SECONDS", "3600"))

ANNOTATION_FUNNEL = "tailscale.com/funnel"
ANNOTATION_EXPOSED_AT = "tailscale-funnel-bot/exposed-at"

_DEFAULT_IGNORED_NAMESPACES = "kube-system,tailscale,funnel-bot,flux-system,longhorn-system"

def _parse_env_list(var_name: str, default: str = "") -> frozenset[str]:
    raw = os.getenv(var_name, default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())

IGNORED_NS = _parse_env_list("IGNORED_NAMESPACES", _DEFAULT_IGNORED_NAMESPACES)
IGNORED_SVC = _parse_env_list("IGNORED_SERVICES")
ALLOWED_SVC = _parse_env_list("ALLOWED_SERVICES")
