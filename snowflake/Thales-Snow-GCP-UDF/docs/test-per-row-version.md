# Test per-row external versions

All reveal definitions now require CONTEXT_HEADERS = (CURRENT_USER). Java reads
sf-context-current-user, trims it and lowercases it with Locale.ROOT before
forwarding it as CRDP username, matching the SPCS username convention.
There is no hardcoded or environment username fallback. Missing, blank, or
duplicate context headers return HTTP 400 before CRDP calls. Protect does not
require the context header. The CRDP policy must authorize the Snowflake username.

Deploy the rebuilt deploy/jar-container/function.jar by building a new Java image
and updating only container java in the existing Cloud Run service. Preserve
Java ingress 8181, CRDP health probe 8080, and CRDP API 8090.

Run deploy/snowflake-with-version.sql after selecting your database/schema and
replacing REPLACE_WITH_EXTERNAL_METADATA_POLICY with a policy that uses external
metadata. The two-argument function shares the existing reveal gateway route;
no new gateway route or integration prefix is needed. SQL was prepared locally;
it has not been executed against Snowflake.

The file also defines the requested underscore names for the one-argument
protect/reveal functions with their existing char-internal policy. Existing
hyphen-named SQL functions remain available. The word external in the function
name refers to the Snowflake external function; the keymetadatalocation header
determines CRDP's actual metadata mode.

For the two-argument reveal function, every nonnull row supplies ciphertext and
external_version as VARCHAR arguments. The per-row version takes precedence
over keymetadata headers and environment variables. A null or blank second
argument is not replaced by the fallback. The supplied SQL uses RETURNS NULL
ON NULL INPUT, so Snowflake returns NULL when either argument is NULL. Blank
versions reaching Java return HTTP 400 before any CRDP calls for the batch.

The one-argument external-metadata reveal still uses keymetadata header first,
then environment. Two arguments are rejected for protect or internal reveal.
Local mock tests verify distinct versions across full/partial batches, fallback
compatibility, header override, and invalid argument rejection.

Use existing externally protected ciphertext and its matching version to test.
The current protect handler reads CRDP's returned external_version but does not
include it in the Snowflake result. This change does not add version capture to
protect results. Existing legacy response/error and row-ID behavior also remains.

Example:

```sql
SELECT thales_gcp_crdp_external_revealbulk_char_with_version(
  email, email_header::VARCHAR
) AS revealed_email
FROM customers;
```
