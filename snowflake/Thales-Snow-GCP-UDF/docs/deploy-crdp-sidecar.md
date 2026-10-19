# CRDP 1.3.1 beside the Snowflake Java handler in Cloud Run

For this proof of concept, a sidecar is the simplest local connection: Java
listens on 8080 and CRDP listens on 8090 within the SAME Cloud Run service
instance. Java calls http://localhost:8090/v1/protectbulk or revealbulk. The
existing gateway hostname, integration audience and backend IAM grant stay in use.
CipherTrust Manager remains a separate dependency, reachable from CRDP over its
configured web interface. Your publicly reachable Manager removes the need for
a static outbound IP for this dependency.

This is a recommended PoC topology, not a claim of Thales certification for
Cloud Run. The current Thales documentation portal was not readable through the
research tool. These steps use the established standalone settings and your
requested 1.3.1 image. Confirm the image tag, /healthz endpoint, token reuse, and
any persistent-storage requirements in your 1.3.1 docs. Cloud Run filesystems
are ephemeral; replacement/scaling can register new CRDP clients. If client
identity must survive container replacement, prefer a VM with persistent storage.

The setup uses instance-based billing (continuous CPU) and one minimum instance
to keep CRDP's heartbeat/policy updates running during idle periods. This incurs
ongoing charges. It initially limits scale to two instances and concurrency to
one. These are PoC choices, not guarantees of a fixed client count. The initial
CRDP allocation is 1 CPU and 1 GiB memory; confirm against the version's sizing
requirements and adjust if needed.

## 1. Upload files and build the updated Java image

Upload the rebuilt deploy/jar-container/function.jar and
deploy/prepare-crdp-sidecar.py to the same paths under ~/deploy in Cloud Shell.
The Java change adds CRDPPORT header/env support, default 8090, allowed 1..65535.
Do not use Java's ingress port 8080 for the sidecar.

In Cloud Shell:

```bash
cd ~
export PROJECT_ID='yourproject'
export REGION='us-central1'
export SERVICE='yourservice'
gcloud config set project "$PROJECT_ID"
export JAVA_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/snowflake-functions/crdp-bulk:sidecar-port-20261013"
gcloud builds submit ./deploy/jar-container --tag="$JAVA_IMAGE"
```

Stop if a command fails. A successful build alone does not change the service.

## 2. Mirror the CRDP 1.3.1 image into Artifact Registry

Use the existing snowflake-functions Docker repository. Cloud Shell normally
provides Docker. Pulling the pinned tag verifies its availability before deployment.

```bash
export CRDP_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/snowflake-functions/crdp:1.3.1"
gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker pull thalesciphertrust/ciphertrust-restful-data-protection:1.3.1
docker tag thalesciphertrust/ciphertrust-restful-data-protection:1.3.1 "$CRDP_IMAGE"
docker push "$CRDP_IMAGE"
```

If the image name/tag differs in your current Thales docs, use that exact image
instead. These instructions pin 1.3.1 as requested; they do not independently
verify that it is the newest release. Mirroring avoids depending on Docker Hub
for each Cloud Run deployment. It does not modify the vendor image.

## 3. Store the registration token

In CipherTrust Manager, use a CRDP application with the required protection
policies (including char-internal), and generate a valid registration token.
Ensure its usage/expiry rules support Cloud Run restarts and multiple clients.
Do not put that token in a SQL header, image or generated service file.

Create the secret once. The prompt hides the token and keeps it out of shell
history; the command stores it in Secret Manager:

```bash
gcloud services enable secretmanager.googleapis.com
read -rsp 'CRDP registration token: ' CRDP_REG_TOKEN; printf '\n'
printf '%s' "$CRDP_REG_TOKEN" | gcloud secrets create crdp-registration-token \
  --replication-policy=automatic --data-file=-
unset CRDP_REG_TOKEN
```

If the secret already exists, use `gcloud secrets versions add
crdp-registration-token --data-file=-` instead of create, and record the new
version number. The setup tool defaults to version 1; change --secret-version
to the number you created, not latest.

Give your existing Cloud Run runtime identity access to THIS secret:

```bash
export RUNTIME_SA="$(gcloud run services describe "$SERVICE" --region="$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')"
printf '%s\n' "$RUNTIME_SA"
gcloud secrets add-iam-policy-binding crdp-registration-token \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
```

Confirm RUNTIME_SA contains the intended email before granting the role. If
blank, resolve the effective runtime account first. All containers in this
service use the same Cloud Run service identity.

## 4. Export and prepare the two-container revision

Save the current revision name for rollback and export its full service spec:

```bash
gcloud run services describe "$SERVICE" --region="$REGION" \
  --format='value(status.latestReadyRevisionName)'
gcloud run services describe "$SERVICE" --region="$REGION" --format=export \
  > deploy/service.before-sidecar.yaml
```

If that backup file already exists, use a different name to retain it.
Install PyYAML if needed, set your Manager hostname/IP, and prepare the new spec:

```bash
python3 -m pip install --user PyYAML
export KEY_MANAGER_HOST='REPLACE_WITH_PUBLIC_CIPHERTRUST_MANAGER_HOST'
python3 deploy/prepare-crdp-sidecar.py deploy/service.before-sidecar.yaml \
  --java-image="$JAVA_IMAGE" --crdp-image="$CRDP_IMAGE" \
  --key-manager-host="$KEY_MANAGER_HOST" --secret-version=1 \
  --crdp-port=8090 --output=deploy/service.sidecar.yaml
```

Use the Manager format prescribed in your Thales version docs. The tool expects
one existing Java container; it will refuse to modify an already multi-container
export. It preserves the existing service identity, app settings and network
configuration, updates the Java image, sets Java CRDPIP=localhost and CRDPPORT,
adds CRDP with REGISTRATION_TOKEN referencing the secret, and adds an HTTP
startup probe for /healthz on port 8080. It refuses to overwrite an existing output file.

If you previously enabled VPC all-traffic egress, it remains in effect. Ensure
that route/NAT still permits CRDP to reach the public CipherTrust Manager.
Local Java-to-CRDP traffic does not require that VPC setup.

Inspect the generated YAML with vi. Only the Java container has a ports section;
this identifies it as the ingress container on 8181. The deployed CRDP image also
occupies 8080, so Java must use a different port. Cloud Run sets Java's PORT to
8181 and the invoker reads it automatically. The sidecar's probe refers
to its health port 8080 without exposing that port externally. Java depends on CRDP passing
its startup probe. The tool assigns all traffic to the new revision when deployed;
retain the prior revision name if you need to revert.

## 5. Deploy and inspect registration

```bash
gcloud run services replace deploy/service.sidecar.yaml \
  --project="$PROJECT_ID" --region="$REGION"
gcloud run services logs read "$SERVICE" --project="$PROJECT_ID" \
  --region="$REGION" --freshness=30m --limit=100
```

CRDP 1.3.1 health checks use port 8080, separate from the protection API port 8090.
The earlier /healthz probe on 8090 returned 404. Keep the CRDP HTTP startup
probe on 8080 and Java ingress/probe on 8181 to avoid their port conflict.
Inspect CRDP registration logs and run a protect/reveal round trip after deployment.

To inspect just CRDP container logs in Logs Explorer, use:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yourservice"
labels."run.googleapis.com/container_name"="crdp"
```

## 6. Update both Snowflake functions and test

In both existing CREATE EXTERNAL FUNCTION definitions, use:

```sql
'CRDPIP' = 'localhost',
'CRDPPORT' = '8090',
```

Keep the other headers, including protection-profile=char-internal, and keep
the echo1 gateway URLs. Recreate both functions. Headers override env values,
so leaving the old EC2 CRDPIP header would bypass the sidecar. The Java variable
is CRDPPORT; the Thales container variable is CRDP_PORT. If changing the port,
update SQL, Java fallback and CRDP_PORT together. Keep the separate CRDP
health startup-probe port at 8080.

Run the protect query and round trip from deploy/snowflake.sql. Then verify
bulk boundaries and errors against the real CRDP 1.3.1 service. The source's
legacy error-response handling still needs hardening; a malformed-response
Snowflake error can hide a downstream CRDP exception. Check container logs.

To roll back the service, use your saved prior revision name:

```bash
gcloud run services update-traffic "$SERVICE" --region="$REGION" \
  --to-revisions=REPLACE_WITH_PREVIOUS_READY_REVISION=100
```

Also restore CRDPIP/CRDPPORT headers to the old destination if rolling back to
an image/revision using remote CRDP. Keep the gateway configuration unchanged.

## References

- [Cloud Run multi-container deployments](https://docs.cloud.google.com/run/docs/deploying#deploying_multiple_containers_to_a_service)
- [Container dependencies and startup order](https://docs.cloud.google.com/run/docs/configuring/services/containers)
- [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Current Thales standalone instructions](https://docs-cybersec.thalesgroup.com/bundle/latest-cdsp-crdp/page/admin/crdp-deploy_alternative/deploy-standalone/index.html)
- [Earlier Thales custom-port instructions](https://thalesdocs.com/ctp/con/crdp/1.1.0/admin/crdp-tasks/crdp-dply-usr-port/index.html)
- [Earlier Thales CRDP health endpoints](https://thalesdocs.com/ctp/con/crdp/1.1.0/admin/crdp-tasks/crdp-probes/index.html)

