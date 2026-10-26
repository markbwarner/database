-- Deploy the rebuilt Java image first. CURRENT_USER is a dynamic context header.
CREATE OR REPLACE EXTERNAL FUNCTION thales_gcp_crdp_external_revealbulk_char(b VARCHAR)
  RETURNS VARIANT
  RETURNS NULL ON NULL INPUT
  VOLATILE
  API_INTEGRATION = my_gcp_integration
  HEADERS = (
    'CRDPIP' = 'localhost',
    'CRDPPORT' = '8090',
    'mode' = 'revealbulk',
    'datatype' = 'char',
    'protection-profile' = 'char-external',
    'keymetadatalocation' = 'external',
    'keymetadata' = '1001000',
    'showrevealinternalkey' = 'yes',
    'returnciphertextforuserwithnokeyaccess' = 'no',
    'usersetlookup' = 'no',
    'BATCHSIZE' = '1000'
  )
  CONTEXT_HEADERS = (CURRENT_USER)
  MAX_BATCH_ROWS = 1000
  COMPRESSION = NONE
  AS 'https://your-gateway.dev/thales-gcp-crdp-revealbulk-char';

SELECT CURRENT_USER();
SELECT thales_gcp_crdp_external_revealbulk_char('sS5NSo81') AS revealed_value;
