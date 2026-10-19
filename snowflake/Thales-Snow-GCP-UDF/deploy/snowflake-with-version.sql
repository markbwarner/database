-- Existing one-argument behavior under the requested names (internal metadata).
CREATE OR REPLACE EXTERNAL FUNCTION thales_gcp_crdp_external_protectbulk_char (b VARCHAR)
  RETURNS VARIANT
  RETURNS NULL ON NULL INPUT
  VOLATILE
  API_INTEGRATION = my_gcp_integration
  HEADERS = (
    'CRDPIP' = 'localhost',
    'CRDPPORT' = '8090',
    'mode' = 'protectbulk',
    'datatype' = 'char',
    'protection-profile' = 'char-internal',
    'keymetadatalocation' = 'internal',
    'showrevealinternalkey' = 'yes',
    'returnciphertextforuserwithnokeyaccess' = 'no',
    'usersetlookup' = 'no',
    'BATCHSIZE' = '1000'
  )
  MAX_BATCH_ROWS = 1000
  COMPRESSION = NONE
  AS 'https://echo1-7g0qje36.uc.gateway.dev/thales-gcp-crdp-protectbulk-char';

CREATE OR REPLACE EXTERNAL FUNCTION thales_gcp_crdp_external_revealbulk_char (b VARCHAR)
  RETURNS VARIANT
  RETURNS NULL ON NULL INPUT
  VOLATILE
  API_INTEGRATION = my_gcp_integration
  HEADERS = (
    'CRDPIP' = 'localhost',
    'CRDPPORT' = '8090',
    'mode' = 'revealbulk',
    'datatype' = 'char',
    'protection-profile' = 'char-internal',
    'keymetadatalocation' = 'internal',
    'showrevealinternalkey' = 'yes',
    'returnciphertextforuserwithnokeyaccess' = 'no',
    'usersetlookup' = 'no',
    'BATCHSIZE' = '1000'
  )
  MAX_BATCH_ROWS = 1000
  COMPRESSION = NONE
  CONTEXT_HEADERS = (CURRENT_USER)
  AS 'https://echo1-7g0qje36.uc.gateway.dev/thales-gcp-crdp-revealbulk-char';
-- Replace the policy placeholder with an actual EXTERNAL-metadata policy.
-- No keymetadata header is needed: each row supplies its own external version.
CREATE OR REPLACE EXTERNAL FUNCTION thales_gcp_crdp_external_revealbulk_char_with_version
  (ciphertext VARCHAR, external_version VARCHAR)
  RETURNS VARIANT
  RETURNS NULL ON NULL INPUT
  VOLATILE
  API_INTEGRATION = my_gcp_integration
  HEADERS = (
    'CRDPIP' = 'localhost',
    'CRDPPORT' = '8090',
    'mode' = 'revealbulk',
    'datatype' = 'char',
    'protection-profile' = 'REPLACE_WITH_EXTERNAL_METADATA_POLICY',
    'keymetadatalocation' = 'external',
    'showrevealinternalkey' = 'yes',
    'returnciphertextforuserwithnokeyaccess' = 'no',
    'usersetlookup' = 'no',
    'BATCHSIZE' = '1000'
  )
  MAX_BATCH_ROWS = 1000
  COMPRESSION = NONE
  CONTEXT_HEADERS = (CURRENT_USER)
  AS 'https://echo1-7g0qje36.uc.gateway.dev/thales-gcp-crdp-revealbulk-char';

-- Replace table/column identifiers with your actual ciphertext/version columns.
-- SELECT thales_gcp_crdp_external_revealbulk_char_with_version(
--   email, email_header::VARCHAR
-- ) AS revealed_email FROM customers;
-- NULL in either argument returns NULL without invoking the service for that row.
