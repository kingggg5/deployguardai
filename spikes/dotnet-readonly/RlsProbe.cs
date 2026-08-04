using Npgsql;

namespace DeployGuard.ReadOnlySpike;

public static class RlsProbe
{
    private const string WorkspaceA = "00000000-0000-0000-0000-000000000010";
    private const string WorkspaceB = "00000000-0000-0000-0000-000000000020";

    public static async Task<RlsParityReport> RunAsync()
    {
        var connectionString = Environment.GetEnvironmentVariable("DOTNET_SPIKE_DATABASE_URL")
            ?? Environment.GetEnvironmentVariable("POSTGRES_TEST_DATABASE_URL");
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            return new RlsParityReport(
                "not-run",
                "Set DOTNET_SPIKE_DATABASE_URL to a non-owner PostgreSQL runtime role to run the read-only probe.",
                false, false, 0, 0, 0);
        }

        try
        {
            await using var dataSource = NpgsqlDataSource.Create(connectionString);
            await using var connection = await dataSource.OpenConnectionAsync();
            await using var transaction = await connection.BeginTransactionAsync();

            var role = await ScalarAsync(connection, transaction,
                "SELECT rolsuper::text || ':' || rolbypassrls::text FROM pg_roles WHERE rolname = current_user");
            var rolePosture = string.Equals(role, "false:false", StringComparison.OrdinalIgnoreCase);
            var rowSecurity = string.Equals(
                await ScalarAsync(connection, transaction,
                    "SELECT row_security_active('audit_events'::regclass)::text"),
                "true", StringComparison.OrdinalIgnoreCase);
            var unscopedRows = await CountAsync(connection, transaction, "SELECT COUNT(*) FROM audit_events");
            await SetTenantContextAsync(connection, transaction, WorkspaceA);
            var workspaceARows = await CountAsync(connection, transaction, "SELECT COUNT(*) FROM audit_events");
            await SetTenantContextAsync(connection, transaction, WorkspaceB);
            var workspaceBRows = await CountAsync(connection, transaction, "SELECT COUNT(*) FROM audit_events");
            await transaction.RollbackAsync();

            var passed = rolePosture
                && rowSecurity
                && unscopedRows == 0
                && workspaceARows == 1
                && workspaceBRows == 1;
            return new RlsParityReport(
                passed ? "pass" : "fail",
                passed
                    ? "Read-only role posture, RLS activation, fail-closed unscoped read, and tenant-scoped counts matched the Python baseline."
                    : "Role posture, row_security_active, fail-closed unscoped read, or tenant-scoped counts did not match the Python baseline.",
                rolePosture, rowSecurity, unscopedRows, workspaceARows, workspaceBRows);
        }
        catch (Exception exception)
        {
            return new RlsParityReport(
                "error",
                $"Read-only probe failed: {exception.GetType().Name}: {exception.Message}",
                false, false, 0, 0, 0);
        }
    }

    private static async Task SetTenantContextAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, string workspaceId)
    {
        await using var command = new NpgsqlCommand(
            "SELECT set_config('deployguard.workspace_id', $1, true)", connection, transaction);
        command.Parameters.AddWithValue(workspaceId);
        await command.ExecuteScalarAsync();
    }

    private static async Task<long> CountAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, string sql)
    {
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        return Convert.ToInt64(await command.ExecuteScalarAsync());
    }

    private static async Task<string?> ScalarAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, string sql)
    {
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        return Convert.ToString(await command.ExecuteScalarAsync());
    }
}
