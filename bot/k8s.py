import time

from kubernetes import client, config

from .config import ANNOTATION_DURATION, ANNOTATION_EXPOSED_AT, ANNOTATION_FUNNEL

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

_v1 = client.CoreV1Api()
_networking = client.NetworkingV1Api()


def get_services(ignored_ns, ignored_svc, allowed_svc) -> list[client.V1Service]:
    all_svcs = _v1.list_service_for_all_namespaces().items
    
    filtered_svcs = []
    for svc in all_svcs:
        name = svc.metadata.name
        namespace = svc.metadata.namespace

        if svc.spec.type != "ClusterIP" or name == "kubernetes" or name.endswith("-funnel"):
            continue

        if name in allowed_svc:
            filtered_svcs.append(svc)
            continue

        if namespace in ignored_ns or name in ignored_svc:
            continue

        filtered_svcs.append(svc)

    return filtered_svcs

def get_active_funnels() -> set[str]:
    active = set()
    for ing in _networking.list_ingress_for_all_namespaces().items:
        ann = ing.metadata.annotations or {}
        if ANNOTATION_EXPOSED_AT in ann:
            active.add(
                f"{ing.metadata.namespace}/"
                f"{ing.metadata.name.removesuffix('-funnel')}"
            )
    return active


def get_all_funnel_ingresses() -> list[client.V1Ingress]:
    return [
        ing
        for ing in _networking.list_ingress_for_all_namespaces().items
        if ing.metadata.name.endswith("-funnel")
    ]


def expose_service(svc_name: str, namespace: str, duration_seconds: int | None = None) -> str:
    original = _v1.read_namespaced_service(name=svc_name, namespace=namespace)
    ports = original.spec.ports
    if not ports:
        raise ValueError(f"Service {namespace}/{svc_name} has no ports defined")

    funnel_name = f"{svc_name}-funnel"
    port = ports[0].port

    annotations = {
        ANNOTATION_FUNNEL: "true",
        ANNOTATION_EXPOSED_AT: str(int(time.time())),
    }
    if duration_seconds is not None:
        annotations[ANNOTATION_DURATION] = str(duration_seconds)

    body = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=funnel_name,
            namespace=namespace,
            annotations=annotations,
        ),
        spec=client.V1IngressSpec(
            ingress_class_name="tailscale",
            rules=[
                client.V1IngressRule(
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=svc_name,
                                        port=client.V1ServiceBackendPort(number=port),
                                    )
                                ),
                            )
                        ]
                    )
                )
            ],
            tls=[client.V1IngressTLS(hosts=[funnel_name])],
        ),
    )

    try:
        _networking.create_namespaced_ingress(namespace=namespace, body=body)
    except client.exceptions.ApiException as e:
        if e.status == 409:
            _networking.replace_namespaced_ingress(
                name=funnel_name, namespace=namespace, body=body
            )
        else:
            raise

    return funnel_name


def close_service(svc_name: str, namespace: str) -> None:
    funnel_name = f"{svc_name}-funnel"
    try:
        ingress = _networking.read_namespaced_ingress(
            name=funnel_name, namespace=namespace
        )
    except client.exceptions.ApiException as e:
        if e.status == 404:
            raise ValueError(f"No active funnel found for {svc_name}")
        raise

    ann = ingress.metadata.annotations or {}
    if ANNOTATION_EXPOSED_AT not in ann:
        raise ValueError(
            f"`{funnel_name}` exists but was not created by funnel-bot, aborting"
        )

    _networking.delete_namespaced_ingress(name=funnel_name, namespace=namespace)


def delete_ingress(name: str, namespace: str) -> None:
    _networking.delete_namespaced_ingress(name=name, namespace=namespace)


def read_ingress(name: str, namespace: str) -> client.V1Ingress:
    return _networking.read_namespaced_ingress(name=name, namespace=namespace)
