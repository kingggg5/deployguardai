# DeployGuard .NET 10 read-only spike

This project is an isolated decision spike, not a second production backend.
It has no write endpoints, no provider credentials, no deployment authority,
and no database writes. Its fixture data is synthetic and copied from the
versioned DeployGuard contract and golden corpus.

## What it proves

- ASP.NET Core 10 can host a read-only vertical slice.
- The deterministic risk, blast-radius, and RCA engines can be ported without
  changing the versioned output contract.
- Five representative GET responses match the captured OpenAPI/read contract.
- The same golden corpus can produce byte-equivalent canonical SHA-256 output.
- A read-only Npgsql probe can verify runtime role posture and fail-closed RLS
  when pointed at a real non-owner PostgreSQL role.
- A same-workload engine microbenchmark can be compared with Python.

## Run the gates

From the repository root:

```powershell
dotnet build spikes/dotnet-readonly/DeployGuard.ReadOnlySpike.csproj -c Release
dotnet run --project spikes/dotnet-readonly/DeployGuard.ReadOnlySpike.csproj -c Release -- --verify --iterations 1000
python scripts/compare_runtime_benchmarks.py --iterations 3000 --repetitions 3
```

The verifier must report `9/9` golden cases and five representative GET
responses. Performance is intentionally labelled as an engine-only
microbenchmark; it is not a production capacity or SLO claim.

The current three-sample local median is Python p95 204.2µs versus .NET p95
305.1µs (1.49× slower). This is evidence against a performance-led rewrite,
not a claim that either runtime is faster for HTTP, database, or worker I/O.

## Optional RLS probe

Set `DOTNET_SPIKE_DATABASE_URL` to a non-owner, non-superuser,
`NOBYPASSRLS` PostgreSQL runtime connection after the schema and test fixtures
exist:

```powershell
$env:DOTNET_SPIKE_DATABASE_URL = "Host=127.0.0.1;Port=5432;Database=deployguard;Username=runtime;Password=replace-me"
dotnet run --project spikes/dotnet-readonly/DeployGuard.ReadOnlySpike.csproj -c Release -- --verify
```

The probe is read-only. It checks `row_security_active`, role posture, an
unscoped fail-closed read, and two transaction-local workspace contexts. It
does not create roles, migrations, fixtures, or application records.

## Migration gate

Do not route production traffic to this project. A migration proposal must
first attach the verifier report and satisfy all of these conditions:

1. 100% golden-corpus parity with zero unexplained differences.
2. Empty or explicitly approved OpenAPI breaking-change report.
3. Security/RLS, authentication, RBAC, replay, and failure-injection parity.
4. A measured operational or performance benefit on the same reference
   workload, not a language preference.
5. Proven backup, restore, migration, observability, and rollback runbooks.

The current spike intentionally does not satisfy the full migration gate:
provider ingress, writes, worker side effects, authentication, and full RLS
CRUD parity remain out of scope.
