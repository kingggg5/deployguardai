\set ON_ERROR_STOP on

-- Local Compose convenience only. Production roles/passwords must be created
-- by the managed database/IAM layer before runtime-role-grants.sql is applied.
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'application_role',
  :'application_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'application_role'
)
\gexec

SELECT format(
  'ALTER ROLE %I PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'application_role',
  :'application_password'
)
\gexec

\ir runtime-role-grants.sql
