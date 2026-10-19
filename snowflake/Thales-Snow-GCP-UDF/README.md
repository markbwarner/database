# Protecting Snowflake data with Thales CADP and CRDP

This project demonstrates how to protect and reveal sensitive data in Snowflake through external functions backed by Thales CipherTrust technologies. The examples use format-preserving encryption (FPE) to retain the character format required by the selected algorithm or protection policy.

Two approaches are provided:

- **CipherTrust Application Data Protection (CADP):** Java handlers use the CADP for Java SDK and its cryptographic provider to encrypt or decrypt values.
- **CipherTrust RESTful Data Protection (CRDP):** a Java handler calls REST APIs to protect or reveal values using protection policies managed in CipherTrust Manager.

Google Cloud hosts the HTTP handlers connecting Snowflake to these Thales interfaces. This README introduces the code; detailed deployment instructions are linked below. These are proof-of-concept examples. Recent header, user-context, and per-row metadata enhancements apply to the CRDP bulk handler and have not been applied to all CADP examples.

## Integration overview

```text
Snowflake SQL -> API Gateway -> Java HTTP handler
                                |
                                +-- CADP for Java SDK -> CipherTrust Manager integration
                                |
                                +-- CRDP REST API -> CipherTrust Manager policies and keys
```

The branches are alternatives. CADP examples do not require a CRDP container. CRDP can run as a separately reachable service or as a sidecar beside Java.

Snowflake sends function arguments as JSON rows. The handler invokes the selected Thales interface and maps results back to Snowflake. "Bulk" describes the Thales operation, not the number of SQL arguments: a single-argument SQL function can process an entire column, and a bulk handler can process one row.

## Classes and responsibilities

| Class | Description | Implementation notes |
| --- | --- | --- |
| [CMUserSetHelper.java](src/main/java/com/example/CMUserSetHelper.java) | Utility for CipherTrust Manager user sets. Authenticates to Manager, checks membership, and supports adding users individually or from a file. | An administration/helper class, not a Snowflake HTTP function. Optional membership lookup calls in the general handlers are currently commented out. |
| [CustomException.java](src/main/java/com/example/CustomException.java) | Carries an exception message and integer error code for application/user-set errors. | Shared support class. It does not itself set HTTP status or build a Snowflake response. |
| [ThalesGCPSnowCADPBulkFPE.java](src/main/java/com/example/ThalesGCPSnowCADPBulkFPE.java) | Encrypts or decrypts Snowflake values through the CADP for Java bulk FPE API. | Uses `NAECipher.doFinalBulk`, splits values into chunks using `BATCHSIZE`, and collects SDK per-element errors. Configuration is environment-based. |
| [ThalesGCPSnowCADPFPE.java](src/main/java/com/example/ThalesGCPSnowCADPFPE.java) | Demonstrates CADP FPE encryption/decryption one value at a time. | Uses Java `Cipher` with `IngrianProvider` and calls `doFinal` for each value. Can receive multiple Snowflake rows without using the SDK bulk operation. |
| [ThalesGCPSnowCRDPBulkFPE.java](src/main/java/com/example/ThalesGCPSnowCRDPBulkFPE.java) | Protects or reveals Snowflake values using CRDP `/v1/protectbulk` and `/v1/revealbulk`. | Current CRDP deployment target. Supports headers/environment fallbacks, Snowflake user context, internal/external metadata, and per-row external versions for reveal. |
| [ThalesGCPSnowCRDPFPE.java — legacy](archive/legacy/ThalesGCPSnowCRDPFPE.java.txt) | Original CRDP example calling `/v1/protect` or `/v1/reveal` once per value. | Retired and archived outside the compiled source tree. Lacks the new header/context handling and must not be deployed as-is. See [archive notes](archive/legacy/README.md). |

Additional CADP classes provide operation/data-type-specific examples. The table focuses on the general CADP and CRDP handlers and shared helpers.

## CADP integration

Both general CADP handlers initialize the provider, establish an `NAESession`, obtain an `NAEKey`, and select an FPE algorithm based on the configured data type. The bulk class submits chunks to the SDK; the non-bulk class applies the cipher to individual values.

| Configuration | Current behavior |
| --- | --- |
| `mode` | Environment value `encrypt` or `decrypt`, rather than CRDP's `protectbulk`/`revealbulk`. |
| `datatype` | Selects the example character/numeric FPE handling. |
| `CMUSER`, `CMPWD` | Credentials used to establish the SDK session. |
| `BATCHSIZE` | Chunk size used by the CADP bulk handler. |
| `CADP_for_JAVA.properties` | SDK configuration loaded from the classpath; review the file in `src/main/resources` for your environment. |

The general CADP examples currently use the sample key name `testfaas` in source. Configure your actual key, SDK connection settings, credentials, and connectivity to CipherTrust Manager. These classes retain their original environment-driven configuration; the CRDP header/context behavior described below does not automatically apply to them.

## CRDP integration

`ThalesGCPSnowCRDPBulkFPE` is the maintained CRDP example and the default target in the Maven function plugin and supplied container Dockerfile.

- `mode` selects `protectbulk` or `revealbulk`.
- The SQL header `protection-profile` selects the policy; its environment fallback is `protection_profile`.
- Settings use Snowflake `sf-custom-*` headers first, then environment fallbacks. `CRDPIP` and `CRDPPORT` identify the CRDP API host/port.
- Reveal requires `CONTEXT_HEADERS = (CURRENT_USER)`. Java trims and lowercases `sf-context-current-user` and passes it as CRDP's `username`. There is no default reveal user; your policy must authorize that user.
- `keymetadatalocation` selects internal or external metadata handling.
- Single-argument external reveal gets the version from `keymetadata` in a header or environment variable. Two-argument reveal takes ciphertext plus a per-row external version, overriding the request-wide fallback.

After creating the two-argument function from the linked SQL examples, you can reveal using matching ciphertext/version columns:

```sql
SELECT thales_gcp_crdp_external_revealbulk_char_with_version(
  email, email_header::VARCHAR
) AS revealed_email
FROM customers;
```

All rows in a request share the configured protection policy; their version arguments can differ. For a single-row HTTP test, the same bulk handler accepts:

```json
{"data":[[0,"ABCD1234"]]}
```

Required settings still come from headers/environment. `BATCHSIZE=1` sends one value per CRDP bulk call; it does not switch to the retired single-value handler. Use Postman or curl directly against CRDP to compare its single-value APIs.

## Deployment and SQL examples

Detailed guides currently live in `docs/`. Scripts, SQL, and container build files are in `deploy/`.

| Guide/example | Purpose |
| --- | --- |
| [Java handler with a separately reachable CRDP service](docs/deploy-snowflake-crdp-gcp.md) | Deploy the Java function/container, configure API Gateway, and integrate with Snowflake. |
| [Java handler with CRDP as a sidecar](docs/deploy-crdp-sidecar.md) | Deploy Java and CRDP together, including secrets, ports, probes, and resource settings. |
| [Single-argument reveal with CURRENT_USER](deploy/snowflake-current-user.sql) | Define reveal with dynamic user context and a fixed external version. |
| [Single- and two-argument functions](deploy/snowflake-with-version.sql) | Define the underscore-named functions and pass external versions per row. |
| [Per-row version behavior](docs/test-per-row-version.md) | Review precedence, NULL handling, and version-related limitations. |

The deployment guides describe CRDP. A CADP deployment needs its selected handler target and SDK configuration in addition to credentials, keys, and Manager connectivity. The supplied Dockerfile starts the CRDP bulk handler; selecting CADP requires changing the target.

Replace example policies, hosts, and values for your environment. In particular, `snowflake-current-user.sql` uses policy `char-external`, version `1001000`, and ciphertext from a test session.

## Build and local verification

The Maven project targets Java 17. Use JDK 17 or a newer JDK capable of targeting Java 17:

```text
mvn clean package -Dmaven.test.skip=true
```

The assembled JAR is `target/CADP-SNOW-GCP-UDF-0.0.2-SNAPSHOT-jar-with-dependencies.jar`. For the supplied CRDP container deployment, copy it to `deploy/jar-container/function.jar` before building the image.

Run CRDP-specific smoke tests separately after packaging:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/test-headers.ps1
```

These tests use local mock servers to check header/env precedence, lowercase user context, external versions, validation, and batching. They require `java` on PATH, the Functions Framework API dependency in the default Windows Maven cache, and local port 8090 available. They do not validate real cryptographic operations, CADP behavior, CipherTrust policy configuration, or cloud authentication.

## Current scope and limitations

- These examples support testing and integration development. Compilation and mock tests do not establish production readiness or compatibility with every algorithm and data format.
- CRDP protection currently returns ciphertext without its external version. Capturing that version for storage requires an additional change.
- Some CRDP downstream failures still produce invalid Snowflake response wrappers or incomplete results. Successful bulk responses synthesize row IDs; arbitrary input IDs and partial failures need hardening.
- The separate Java userset lookup calls are commented out in the general handlers. Setting `usersetlookup` does not activate them. CRDP receives the reveal username for evaluation by its configured access policy.
- CADP examples have not received the CRDP header/context enhancements or equivalent test coverage.
- `CMUserSetHelper` includes development-oriented certificate-validation overrides; review its connection handling before operational use.
- The archived non-bulk CRDP source is historical reference, not a release target.
