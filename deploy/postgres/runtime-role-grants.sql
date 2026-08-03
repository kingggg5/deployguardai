\set ON_ERROR_STOP on

-- Required psql variables:
--   --set=schema_owner=deployguard_owner
--   --set=application_role=deployguard_app
-- Both roles must already be provisioned by the managed database/IAM layer.
\if :{?schema_owner}
\else
  \echo 'schema_owner psql variable is required'
  \quit 2
\endif
\if :{?application_role}
\else
  \echo 'application_role psql variable is required'
  \quit 2
\endif

SELECT
  EXISTS(
    SELECT 1 FROM pg_roles WHERE rolname = :'application_role'
  ) AS role_exists,
  COALESCE(
    (
      SELECT rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole
      FROM pg_roles
      WHERE rolname = :'application_role'
    ),
    true
  ) AS unsafe_role
\gset

\if :role_exists
\else
  \echo 'application_role does not exist'
  \quit 2
\endif
\if :unsafe_role
  \echo 'application_role has unsafe PostgreSQL role attributes'
  \quit 3
\endif

SELECT pg_has_role(
  :'application_role',
  :'schema_owner',
  'MEMBER'
) AS inherits_schema_owner
\gset

\if :inherits_schema_owner
  \echo 'application_role must not inherit or be a member of schema_owner'
  \quit 3
\endif

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM :"application_role";
GRANT CONNECT ON DATABASE :"DBNAME" TO :"application_role";
GRANT USAGE ON SCHEMA public TO :"application_role";
GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public
  TO :"application_role";
GRANT USAGE, SELECT
  ON ALL SEQUENCES IN SCHEMA public
  TO :"application_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"application_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"application_role";

-- Deliberately omitted: CREATE, TRUNCATE, REFERENCES, TRIGGER, role membership,
-- table ownership, SUPERUSER, BYPASSRLS, CREATEDB, and CREATEROLE.
