using System.Text.Json;

namespace DeployGuard.ReadOnlySpike;

public sealed record GoldenCase(string Id, string Engine, JsonElement Input,
    JsonElement ExpectedSummary, string ExpectedSha256);

public sealed record GoldenCorpus(string Schema, string Version,
    IReadOnlyList<GoldenCase> Cases)
{
    public static GoldenCorpus Load(string baseDirectory)
    {
        var path = Path.Combine(baseDirectory, "corpus", "golden-corpus-v1.json");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        var root = document.RootElement;
        var cases = root.GetProperty("cases").EnumerateArray()
            .Select(item => new GoldenCase(
                item.GetProperty("id").GetString()!,
                item.GetProperty("engine").GetString()!,
                item.GetProperty("input").Clone(),
                item.GetProperty("expected_summary").Clone(),
                item.GetProperty("expected_sha256").GetString()!))
            .ToArray();
        return new GoldenCorpus(
            root.GetProperty("schema").GetString()!,
            root.GetProperty("version").GetString()!,
            cases);
    }
}

public sealed class ReadOnlySpikeStore
{
    private readonly Dictionary<string, JsonElement> _responsesByName = new(StringComparer.Ordinal);
    private readonly Dictionary<string, JsonElement> _responsesByPath = new(StringComparer.Ordinal);

    public ReadOnlySpikeStore(string baseDirectory)
    {
        var path = Path.Combine(baseDirectory, "contracts", "representative-responses.json");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        foreach (var response in document.RootElement.GetProperty("responses").EnumerateArray())
        {
            var name = response.GetProperty("name").GetString()!;
            var requestPath = response.GetProperty("request").GetProperty("path").GetString()!;
            var body = response.GetProperty("body").Clone();
            _responsesByName[name] = body;
            _responsesByPath[requestPath] = body;
        }
    }

    public JsonElement Response(string name) => _responsesByName[name];

    public JsonElement? ResponseByPath(string path) =>
        _responsesByPath.TryGetValue(path, out var value) ? value : null;
}

public sealed record GateResult(string Name, string Status, string Details);

public sealed record GoldenParityReport(
    int Total,
    int PassedCases,
    int FailedCases,
    IReadOnlyList<string> Failures,
    bool Passed);

public sealed record ContractParityReport(
    string Scope,
    int EndpointsChecked,
    int ResponsesChecked,
    IReadOnlyList<string> Differences,
    bool Passed);

public sealed record RlsParityReport(
    string Status,
    string Details,
    bool RolePosture,
    bool RowSecurity,
    long UnscopedRows,
    long WorkspaceARows,
    long WorkspaceBRows);

public sealed record BenchmarkReport(
    int Iterations,
    int Operations,
    double P50Microseconds,
    double P95Microseconds,
    double P99Microseconds,
    double OperationsPerSecond,
    string Workload);

public sealed record SpikeReport(
    bool Passed,
    string Runtime,
    string DataMode,
    string Scope,
    GoldenParityReport GoldenCorpus,
    ContractParityReport OpenApi,
    RlsParityReport Rls,
    BenchmarkReport Performance,
    IReadOnlyList<GateResult> Gates);
