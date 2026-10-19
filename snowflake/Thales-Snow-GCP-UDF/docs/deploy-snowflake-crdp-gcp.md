# Deploy the Snowflake CRDP bulk function on GCP

One deployment can handle protectbulk and revealbulk. No public GitHub
repository or Docker Hub account is required. Cloud Run functions build an image
for you, or an explicit JAR container can live in private Artifact Registry.
Both support environment variables. No live cloud resources have been changed.

## Local changes and compatibility

The POM now targets Java 17 and CADP `8.18.0.001`. The local function target is
`com.example.yourservice`. Removed the old Ingrian 8.12 dependency
that duplicates CADP classes, and a duplicate OkHttp declaration. The handler
now reads eleven settings (including CRDPIP, CRDPPORT and keymetadata) from `sf-custom-` headers first, then the matching
environment variables. Settings stay local to each request. Blank or duplicate
headers are rejected rather than silently falling back. Values are trimmed;
enum/yes-no values ignore case, while protection policy names and keymetadata preserve case.

Changing a POM cannot update a prebuilt JAR. Use the rebuilt
`target/CADP-SNOW-GCP-UDF-0.0.2-SNAPSHOT-jar-with-dependencies.jar`. An old Java 11
JAR generally loads on a newer JVM, but library and crypto behavior still need
testing. The CRDP bulk class uses REST, not the CADP Java crypto API; CADP serves
the other handlers in this project. Compilation does not certify encryption
behavior in GCP. The supplied handler remains proof-of-concept code.

Local verification: Maven packaging succeeded on Java 21 targeting Java 17.
A mock CRDP HTTP server confirmed that both mode headers select the correct
downstream path and that protectbulkd returns HTTP 400 without calling CRDP.
The expanded header smoke test also passed environment fallback/precedence,
mixed-case header names, profile JSON escaping, metadata stripping, external
metadata selection, two-row batches with a final partial batch, and validation.
This did not test the real CRDP service, Java 17 runtime, container build,
gateway authentication or Snowflake queries.

## 1. Find the actual gateway and preserve its routes

In GCP API Gateway, distinguish the API ID from the gateway ID.
`demo-api-id-for-udf` appears to be an API ID. Several different
gateway.dev hosts in your examples suggest multiple gateways under that API.

Each gateway serves ONE config. The configs named echo1, testapi, etc. do not
combine automatically. Select the gateway hostname you want to keep, record its
region and active config, and recover that config's original OpenAPI file.
Copy it to `deploy/openapi.merged.yaml`. Preserve all existing paths, backends,
security definitions and top-level settings, including any BigQuery routes.

In Snowflake save the output of:

```sql
DESC API INTEGRATION my_gcp_integration;
```

Record API_GCP_SERVICE_ACCOUNT, GOOGLE_AUDIENCE, and ALL API_ALLOWED_PREFIXES.
Keep the audience exactly as configured, without adding the space in the pasted
example. The Snowflake account authenticates TO the gateway; the GCP backend
service account authenticates FROM the gateway to Cloud Run. These differ.

All gcloud commands below are Bash for GCP Cloud Shell:

```bash
export PROJECT_ID='REPLACE_WITH_PROJECT_ID'
export REGION='us-central1'
export API_ID='demo-api-id-for-udf'
gcloud config set project "$PROJECT_ID"
gcloud api-gateway gateways list --project="$PROJECT_ID"
gcloud api-gateway api-configs list --api="$API_ID" --project="$PROJECT_ID"

export GATEWAY_ID='REPLACE_WITH_ACTUAL_GATEWAY_ID'
export GATEWAY_REGION='REPLACE_WITH_GATEWAY_REGION'
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID"
```

If the original spec is lost, inspect the active config with
`gcloud api-gateway api-configs describe CONFIG_ID --api="$API_ID" --view=FULL
--format=json`. Recover any base64 OpenAPI document contents; do not upload the
resource JSON as an OpenAPI spec. Verify recovered routes against the live API.

If your FULL exports are saved as `.yml` files, upload `deploy/recover-openapi.py`
to the existing deploy folder in Cloud Shell. From the directory containing
those `.yml` files, run:

```bash
python3 deploy/recover-openapi.py
```

It processes all top-level `.yml` files and creates separate recovered specs
under `deploy/recovered-openapi/`. It accepts JSON exports even with a `.yml`
extension, copies recognizable OpenAPI YAML, and decodes base64 documents. YAML
config exports require PyYAML; if missing, the script explains how to install it.
The existing deploy directory is reused. Inputs are unchanged; existing outputs
with identical contents are skipped and conflicting contents are not overwritten.
Files without OpenAPI documents are reported as errors; other files still process.
No configs are combined or deployed automatically.

Each output is named `INPUT_STEM--1.yaml` (or --2 etc. for multiple documents).
For example `echo-1.yml` produces `deploy/recovered-openapi/echo-1--1.yaml`.
Match the printed config identity to the selected gateway's active config.
Only after selecting the correct output, make a working copy:

```bash
# EXAMPLE ONLY: use echo-1 only if it is the chosen gateway's active config.
cp -n deploy/recovered-openapi/echo-1--1.yaml deploy/openapi.merged.yaml
```

If openapi.merged.yaml already exists, `cp -n` leaves it alone. Inspect it before
editing to ensure it came from the selected active config. Retain the original
recovered output unchanged and add the two new routes to the working copy.

## 2. Build and configure

In Windows PowerShell from this project:

```powershell
mvn package '-Dmaven.test.skip=true'
```

This builds the project but does not execute the standalone demo test programs.
Use Java 17 or later. Compilation on Java 21 with source/target 17 alone does
not prove Java 17 runtime compatibility.

Copy `deploy/env.example.yaml` to `deploy/env.yaml`; set the CRDP host and
protection policy fallback. When both UDFs send all ten headers, those ten
environment settings can be omitted. External keymetadata can be supplied with
the 'keymetadata' SQL header or the matching environment variable (header wins).
Credentials remain environment settings. CRDPIP is a hostname/IP WITHOUT protocol or port: this code
constructs `http://CRDPIP:CRDPPORT/v1/protectbulk` or `/v1/revealbulk`, defaulting
to port 8090. Configure VPC connectivity/firewall access to the selected port
if CRDP is private; match the networking
of a working CRDP function. If your CRDP setup needs TLS or authentication,
adapt the existing HTTP client: it currently uses plain HTTP and no CRDP token.

Keep showrevealinternalkey=yes for round-trip tests. Removing the internal
metadata prefix can prevent reveal. For external metadata set
keymetadatalocation=external and keymetadata to the correct version for the
ciphertext. The existing return discards the separate external_version, so mixed
versions require explicit metadata storage and a richer reveal interface.

## 3A. Deploy as a function; GCP builds the image

Choose this route OR 3B. In the GCP Console choose Cloud Run's function creation
workflow, Java 17, HTTP trigger, authenticated access, and entry point
`com.example.yourservice`. Set the variables from env.yaml in the
runtime configuration. Use the available source-upload workflow with pom.xml
and src/main; pom.xml must be at the archive root. UI options vary by workflow.

For reproducible deployment, upload ONLY pom.xml and src/main to a clean
`function-source` directory in Cloud Shell. Do not upload dotenv.txt, demo test
sources or old JARs. Upload your filled deploy/env.yaml separately. This source
path resolves dependencies from Maven repositories; it no longer needs the
removed local Ingrian artifact.

```bash
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com \
  apigateway.googleapis.com servicemanagement.googleapis.com servicecontrol.googleapis.com

export RUNTIME_SA='REPLACE_WITH_RUNTIME_SERVICE_ACCOUNT_EMAIL'
gcloud functions deploy yourservice \
  --gen2 --region="$REGION" --runtime=java17 \
  --entry-point=com.example.yourservice \
  --source=./function-source --trigger-http --no-allow-unauthenticated \
  --service-account="$RUNTIME_SA" --env-vars-file=./deploy/env.yaml \
  --memory=512Mi --timeout=120s

gcloud functions describe yourservice \
  --gen2 --region="$REGION" --format='yaml(serviceConfig.uri,serviceConfig.service)'
```

Record serviceConfig.uri and the underlying Cloud Run service name. Use that
URI for both gateway backend address and backend JWT audience. The deployer
needs deploy permissions and permission to act as the runtime service account;
the build identity needs build, logging and artifact permissions per Google's
deployment prerequisites. Organization policies can affect these permissions.

## 3B. Deploy the existing fat JAR as a private Cloud Run container

The fat JAR has no application main entry point/web server. The provided
Dockerfile wraps it with Google's Java Functions Framework invoker, which listens
on Cloud Run's PORT and calls your HttpFunction. Cloud Build builds the image;
you do not need Docker installed locally or a public image repository.
The invoker is pinned to Maven Central's published version 1.3.1. The earlier
Dockerfile incorrectly referenced 1.3.2, which is absent from Maven Central;
replace both occurrences in previously uploaded Dockerfiles before rebuilding.

Stage the rebuilt JAR on Windows:

```powershell
Copy-Item -LiteralPath 'target/CADP-SNOW-GCP-UDF-0.0.2-SNAPSHOT-jar-with-dependencies.jar' -Destination 'deploy/jar-container/function.jar'
```

Upload deploy/jar-container and your filled deploy/env.yaml to Cloud Shell.
The staging directory ignore files admit only Dockerfile and function.jar into
the container build, avoiding unrelated workspace files.

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com apigateway.googleapis.com \
  servicemanagement.googleapis.com servicecontrol.googleapis.com

# Create once, or reuse an existing Docker repository.
gcloud artifacts repositories create snowflake-functions \
  --repository-format=docker --location="$REGION"

export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/snowflake-functions/crdp-bulk:java17-cadp818001"
gcloud builds submit ./deploy/jar-container --tag="$IMAGE"

export RUNTIME_SA='REPLACE_WITH_RUNTIME_SERVICE_ACCOUNT_EMAIL'
gcloud run deploy yourservice \
  --image="$IMAGE" --region="$REGION" --no-allow-unauthenticated \
  --service-account="$RUNTIME_SA" --env-vars-file=./deploy/env.yaml \
  --memory=512Mi --timeout=120s --concurrency=1

gcloud run services describe yourservice \
  --region="$REGION" --format='value(status.url)'
```

Your application image stays private. Cloud Build pulls public Maven/JRE base
images; your code need not be public. Use a new image tag per rebuild for clear
rollback history. The Dockerfile has not been built locally; gcloud and Docker
were unavailable in this workspace.

## 4. Permit gateway invocation

Reuse the active config's backend service account so it retains permissions
on all existing backends. A new account needs permission for every preserved
route. Grant Cloud Run Invoker on the new backend; do not make it public.

In Cloud Shell, find the selected gateway's active API config:

```bash
export PROJECT_ID='your-project'
export REGION='us-central1'
export API_ID='demo-api-id-for-udf'
gcloud api-gateway gateways list --project="$PROJECT_ID" \
  --format='table(name,defaultHostname,apiConfig)'
```

The selected gateway's apiConfig ends in `/configs/CONFIG_ID`. Replace the
placeholder below with that actual config ID to read its backend identity:

```bash
export ACTIVE_CONFIG='REPLACE_WITH_ACTIVE_CONFIG_ID'
export GATEWAY_SA="$(gcloud api-gateway api-configs describe "$ACTIVE_CONFIG" \
  --api="$API_ID" --project="$PROJECT_ID" \
  --format='value(gatewayServiceAccount)')"
printf '%s\n' "$GATEWAY_SA"
```

Confirm that the result is a service account email before continuing. If blank
or a resource path rather than an email, resolve the account before granting
access. This is the gateway backend identity, separate from the runtime identity
and Snowflake's API_GCP_SERVICE_ACCOUNT.

For the JAR/container deployment in step 3B, the Cloud Run service name is
`yourservice`. RUN_SERVICE takes the name, **not the HTTPS URL**:

```bash
export RUN_SERVICE='yourservice'
gcloud run services describe "$RUN_SERVICE" \
  --region="$REGION" --project="$PROJECT_ID" \
  --format='yaml(metadata.name,status.url)'

gcloud run services add-iam-policy-binding "$RUN_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$GATEWAY_SA" --role=roles/run.invoker
```

If the service name is not found, run `gcloud run services list
--project="$PROJECT_ID" --region="$REGION"` and select the actual deployed
service name. For step 3A, obtain the underlying name from serviceConfig.service
in the function describe output, using the final segment after `/services/`.
Building an image alone does not deploy a Cloud Run service.

Keep the HTTPS service URL for the gateway backend address and jwt_audience
in step 5. Console equivalent: grant the gateway backend service account
Cloud Run Invoker on the new backend service.

Ingress must allow API Gateway to reach the authenticated endpoint;
an internal-only ingress setting can block the gateway.

## 5. Extend the active gateway configuration

MERGE deploy/gateway-additions.example.yaml into deploy/openapi.merged.yaml.
Add entries under the EXISTING paths and securityDefinitions keys; do not create
duplicate YAML keys. Preserve every old route and security setting. Replace:

- Backend address and jwt_audience with the Cloud Run URL from 3A/3B.
- Issuer and JWKS identity with Snowflake API_GCP_SERVICE_ACCOUNT from DESC.
- x-google-audiences with the unchanged Snowflake GOOGLE_AUDIENCE.

Both paths target the same backend root via CONSTANT_ADDRESS. The handler
uses the forwarded sf-custom-mode header to select the CRDP operation. Gateway
JWT audience is the existing Snowflake value; backend JWT audience is the Cloud
Run URL. They have different purposes.

Create an immutable config under the existing API, inspect it, then update the
selected existing gateway. Creating a config alone changes no live traffic.

```bashe
export NEW_CONFIG='snowflake-crdp-bulk-20261012-v1'
gcloud api-gateway api-configs create "$NEW_CONFIG" \
  --api="$API_ID" --openapi-spec=./deploy/openapi.merged.yaml \
  --backend-auth-service-account="$GATEWAY_SA" --project="$PROJECT_ID"

gcloud api-gateway gateways update "$GATEWAY_ID" \
  --api="$API_ID" --api-config="$NEW_CONFIG" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --format='value(defaultHostname)'
```

Console equivalent: create a new config by uploading the merged OpenAPI file
on the existing API and selecting the backend service account, then edit the
selected gateway to use it. Keep the old config ID to roll back with gateways
update. The existing gateway hostname stays the endpoint. Updating one gateway
does not update the other gateways under that API.

## 6. Update Snowflake and create both functions

Edit deploy/snowflake.sql. Replace the gateway hostname with defaultHostname
from step 5. Fill in the commented ALTER with EVERY current allowed prefix plus
the two new route prefixes, then run it. SET API_ALLOWED_PREFIXES replaces the
entire list; preserve all current entries. If the integration already allows
the entire chosen gateway URL, an addition may be unnecessary. Keep its audience
and identity; do not replace the integration.

Execute the two CREATE statements. They fix the pasted examples: distinct
protect/reveal function names, double quotes around hyphenated identifiers,
HEADERS before AS, no URL spaces, and protectbulk rather than protectbulkd.
Snowflake turns HEADERS ('mode'='protectbulk') into HTTP sf-custom-mode.

The definitions start with MAX_BATCH_ROWS=1 for connectivity testing and
COMPRESSION=NONE because this handler reads JSON directly. This starting setting
is not bulk throughput tuning. Increase the row maximum after batch tests pass.
Select your database/schema and appropriate role first; grant USAGE on the
integration to the creator and on each function to intended callers as needed.
Restrict reveal function USAGE to the intended Snowflake roles.

## 7. Verify behavior

Run both SELECT examples in deploy/snowflake.sql, including the round trip.
Retest all old gateway routes and BigQuery integrations. Increase MAX_BATCH_ROWS
and test 1, BATCHSIZE-1, BATCHSIZE, BATCHSIZE+1 and multiple CRDP batches, nulls,
empty strings, and CRDP errors. Snowflake needs the same input row IDs and one
output per input in a top-level data array. Compilation proves no remote behavior.

Inspection found remaining proof-of-concept issues: synthesized sequential output
row IDs, string-built payload JSON, some failures returned inside HTTP-200 bodies,
and legacy error handling. Reveal username is
hardcoded to snowflakeuser and the userset lookup is commented out. Setting
usersetlookup alone does not enable user authorization. Missing/error rows,
authorization and crypto edge cases need hardening before production.

For 401/403 identify the failing hop: gateway JWT issuer/audience or backend
Cloud Run Invoker. For timeout verify CRDP host/network/port and batch latency.
For malformed JSON or row-count errors inspect handler output instead of changing
the integration.

The handler now writes one structured `CRDP connection target` log after
validating settings, before processing data. It includes crdpHost, crdpPort,
crdpUrl, hostSource (header/environment), portSource (header/environment/default),
the Cloud Run revision, and the Snowflake batch ID when supplied. It does not
include input data, credentials, or authentication headers. Deploy the rebuilt
image containing this log, then rerun a query and inspect:

```bash
gcloud run services logs read yourservice \
  --project=your-project --region=us-central1 \
  --freshness=10m --limit=50
```

If the new log is absent, first confirm the active revision is serving the
updated image. A config-validation error returns before emitting the target log.
Compare the effective URL with the working backend, not just environment values:
a supplied UDF header wins over the environment. A saved Revision YAML describes
one revision and does not show whether the service currently routes traffic to it.

## Supported headers

| Setting | Recommendation |
| --- | --- |
| mode | sf-custom-mode: protectbulk or revealbulk. |
| protection_profile | SQL header protection-profile becomes sf-custom-protection-profile: nonempty, case-sensitive policy name, JSON escaped. Environment remains protection_profile. |
| datatype | sf-custom-datatype: char, charint or nbr. |
| keymetadatalocation | sf-custom-keymetadatalocation: internal or external. Protect/reveal metadata must match. |
| showrevealinternalkey | sf-custom-showrevealinternalkey: yes or no; defaults to yes if neither header nor env exists. |
| returnciphertextforuserwithnokeyaccess | sf-custom-returnciphertextforuserwithnokeyaccess: yes or no, controls the existing fallback branch. |
| usersetlookup | sf-custom-usersetlookup: yes or no is parsed, but the existing userset lookup remains commented out. This header does not enable authorization. |
| keymetadata | sf-custom-keymetadata overrides environment keymetadata. For external reveal, a second VARCHAR argument supplies each row's version and takes precedence over both. Without the second argument, keymetadata is required. Preserves case. |
| BATCHSIZE | sf-custom-BATCHSIZE (case-insensitive): positive integer, capped at 10000. Separate from Snowflake MAX_BATCH_ROWS. |
| CRDPIP | sf-custom-CRDPIP: required hostname/IP, header overrides environment. No protocol, port, path, query or credentials; bracket IPv6. |
| CRDPPORT | sf-custom-CRDPPORT: integer 1..65535, overrides environment CRDPPORT; defaults to 8090 if neither is supplied. |
| usersetlookupip | Remains environment-only. |
| CMUSER, CMPWD, tokens | Keep server-side, use Secret Manager if needed, never UDF headers. |

All ten headers are included in deploy/snowflake.sql, using char-internal as
the example protection policy. Replace it if your actual policy differs.
Snowflake forbids underscores in header names: use protection-profile in SQL,
not protection_profile. The environment name remains unchanged. The handler
also accepts the old underscore spelling for direct non-Snowflake callers,
but rejects requests supplying both spellings. Previously deployed images must
be rebuilt and redeployed to recognize the new header spelling.
Except showrevealinternalkey, CRDPPORT and keymetadata, each setting must exist in a header or environment;
missing/invalid settings return HTTP 400 before CRDP is called. No other settings
can be overridden by headers. HEADERS values are owner-defined constants, not
per-row expressions. Per-row settings need extra arguments and parsing of the
extra Snowflake row columns. Headers select behavior; gateway JWT authentication
and Snowflake function grants control access.

If protect and reveal need different credentials or network permissions, deploy
two services from the SAME image with different configuration/identity. You need
not build two different containers. Common credentials/policy and mode headers
allow the single service requested here.

## Set or update an environment variable after deployment

Environment variables belong to the Cloud Run service revision; no image rebuild
is necessary. To fix a missing CRDPIP on the currently deployed image, run in
Cloud Shell after replacing YOUR_CRDP_HOST with a reachable hostname/IP:

```bash
gcloud run services update yourservice \
  --project=your-project --region=us-central1 \
  --update-env-vars=CRDPIP=YOUR_CRDP_HOST
```

This preserves other variables and creates a new revision. Console equivalent:
Cloud Run service, Edit & deploy new revision, Variables & Secrets, add CRDPIP,
then Deploy. If using CRDPIP headers instead, first deploy the rebuilt image
containing header support, replace the CRDPIP placeholders in both SQL function
definitions, and recreate those functions. Gateway configuration is unchanged.

For CRDPPORT, use --update-env-vars=CRDPPORT=8090 or the SQL header
'CRDPPORT'='8090'. The Thales container uses the distinct variable CRDP_PORT.
For colocating CRDP 1.3.1 inside this service, follow [the sidecar guide](deploy-crdp-sidecar.md).

## Official references

- [Function deployment and automatic image builds](https://cloud.google.com/run/docs/deploy-functions)
- [Java Functions Framework: JAR invoker](https://github.com/GoogleCloudPlatform/functions-framework-java)
- [gcloud functions deploy](https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy)
- [API Gateway deployment model](https://cloud.google.com/api-gateway/docs/deployment-model)
- [Create API configs and backend identity](https://docs.cloud.google.com/api-gateway/docs/creating-api-config)
- [Snowflake GCP console workflow](https://docs.snowflake.com/en/sql-reference/external-functions-creating-gcp-ui)
- [Snowflake external function syntax and headers](https://docs.snowflake.com/en/sql-reference/sql/create-external-function)
- [Snowflake GCP JWT troubleshooting](https://docs.snowflake.com/en/sql-reference/external-functions-creating-gcp-troubleshooting)
- [Thales CADP 8.18 Maven coordinates](https://www.thalesdocs.com/ctp/con/cadp/cadp-java/8.18.0/admin/cadp-for-java-quick-start/index.html)
