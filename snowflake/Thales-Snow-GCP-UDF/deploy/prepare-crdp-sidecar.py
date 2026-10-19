#!/usr/bin/env python3
"""Prepare a Cloud Run sidecar revision from an exported service; does not deploy."""
import argparse
import json
import re
from pathlib import Path
import yaml


class ServiceLoader(yaml.SafeLoader):
    """Preserve yes/no/on/off strings in exported environment settings."""
    yaml_implicit_resolvers = {
        key: [(tag, pattern) for tag, pattern in values
              if tag != "tag:yaml.org,2002:bool"]
        for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }


ServiceLoader.add_implicit_resolver("tag:yaml.org,2002:bool",
                                   re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"),
                                   list("tTfF"))


def normalize_strings(service):
    """Cloud Run env values and metadata maps require strings, unlike traffic flags."""
    def as_string(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    for metadata in (service.get("metadata", {}),
                     service["spec"]["template"].get("metadata", {})):
        for field in ("annotations", "labels"):
            if field in metadata:
                metadata[field] = {key: as_string(value)
                                   for key, value in metadata[field].items()}
    for container in service["spec"]["template"]["spec"]["containers"]:
        for entry in container.get("env", []):
            if "value" in entry:
                entry["value"] = as_string(entry["value"])
    return service


def prepare(service, java_image, crdp_image, manager, secret, secret_version, port):
    if not 1 <= port <= 65535 or port in (8080, 8181):
        raise ValueError("CRDP port must be 1..65535 and avoid 8080 and Java ingress port 8181")
    if service.get("kind") != "Service" or service.get("apiVersion") != "serving.knative.dev/v1":
        raise ValueError("expected gcloud run services describe --format=export YAML")
    revision = service["spec"]["template"]
    containers = revision["spec"]["containers"]
    if len(containers) != 1:
        raise ValueError("expected one existing Java container; do not run on an already modified sidecar export")
    app = containers[0]
    app_name = app.setdefault("name", "java")
    app["image"] = java_image
    if app_name == "crdp":
        raise ValueError("existing Java container cannot be named crdp")
    # CRDP also occupies 8080 in the deployed image; containers share ports.
    # The invoker uses Cloud Run's PORT environment variable automatically.
    app["ports"] = [{"containerPort": 8181}]
    app["startupProbe"] = {"tcpSocket": {"port": 8181},
                           "timeoutSeconds": 2, "periodSeconds": 5, "failureThreshold": 48}
    env = [item for item in app.get("env", []) if item["name"] not in ("CRDPIP", "CRDPPORT", "PORT")]
    app["env"] = env + [{"name": "CRDPIP", "value": "localhost"},
                         {"name": "CRDPPORT", "value": str(port)}]
    annotations = revision.setdefault("metadata", {}).setdefault("annotations", {})
    annotations["run.googleapis.com/container-dependencies"] = json.dumps({app_name: ["crdp"]})
    annotations["run.googleapis.com/cpu-throttling"] = "false"
    annotations["autoscaling.knative.dev/minScale"] = "1"
    annotations["autoscaling.knative.dev/maxScale"] = "2"
    # Remove a fixed revision name so replacement creates a new revision.
    revision["metadata"].pop("name", None)
    revision["spec"]["containerConcurrency"] = 1
    containers.append({
        "name": "crdp", "image": crdp_image,
        # Initial PoC allocation, not a Thales-certified sizing recommendation.
        "resources": {"limits": {"cpu": "1", "memory": "1Gi"}},
        "env": [
            {"name": "KEY_MANAGER_HOST", "value": manager},
            {"name": "REGISTRATION_TOKEN", "valueFrom": {"secretKeyRef": {
                "name": secret, "key": secret_version}}},
            {"name": "SERVER_MODE", "value": "no-tls"},
            {"name": "CRDP_PORT", "value": str(port)}
        ],
        # CRDP 1.3.1 serves health probes separately from the protection API.
        "startupProbe": {"httpGet": {"path": "/healthz", "port": 8080},
                         "timeoutSeconds": 2, "periodSeconds": 5, "failureThreshold": 48}
    })
    # A saved spec can point traffic at the old revision. Explicitly select new.
    service["spec"]["traffic"] = [{"latestRevision": True, "percent": 100}]
    service.pop("status", None)
    for field in ("uid", "resourceVersion", "generation", "creationTimestamp", "selfLink", "managedFields"):
        service["metadata"].pop(field, None)
    return normalize_strings(service)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--output", default="deploy/service.sidecar.yaml")
    parser.add_argument("--java-image", required=True)
    parser.add_argument("--crdp-image", required=True)
    parser.add_argument("--key-manager-host", required=True)
    parser.add_argument("--registration-secret", default="crdp-registration-token")
    parser.add_argument("--secret-version", default="1")
    parser.add_argument("--crdp-port", type=int, default=8090)
    args = parser.parse_args()
    service = yaml.load(Path(args.source).read_text(), Loader=ServiceLoader)
    prepared = prepare(service, args.java_image, args.crdp_image, args.key_manager_host,
                       args.registration_secret, args.secret_version, args.crdp_port)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a user's edited or already prepared revision.
    with output.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(prepared, stream, sort_keys=False)
    print(f"Prepared {output}; review it before running gcloud run services replace.")


if __name__ == "__main__":
    main()
