using System.Diagnostics;
using System.Text.Json;

namespace DeployGuard.ReadOnlySpike;

public static class SpikeVerifier
{
    public static async Task<SpikeReport> RunAsync(string baseDirectory, int iterations = 1_000)
    {
        var corpus = GoldenCorpus.Load(baseDirectory);
        var golden = VerifyGolden(corpus);
        var contracts = VerifyContracts(baseDirectory);
        var rls = await RlsProbe.RunAsync();
        var performance = Benchmark(corpus, iterations);
        var gates = new List<GateResult>
        {
            new("golden-corpus", golden.Passed ? "pass" : "fail",
                $"{golden.PassedCases}/{golden.Total} cases match canonical output hashes."),
            new("openapi-read-only-slice", contracts.Passed ? "pass" : "fail",
                $"{contracts.ResponsesChecked} representative responses and {contracts.EndpointsChecked} GET routes checked."),
            new("postgres-rls-read-only-probe", rls.Status,
                rls.Details),
            new("performance", "measured",
                $"C# read-only engine p95={performance.P95Microseconds:F2}µs over {performance.Operations} operations."),
        };
        var passed = golden.Passed && contracts.Passed && rls.Status is "pass" or "not-run";
        return new SpikeReport(
            passed,
            "dotnet-10",
            "synthetic",
            "read-only vertical slice; no production authority",
            golden,
            contracts,
            rls,
            performance,
            gates);
    }

    private static GoldenParityReport VerifyGolden(GoldenCorpus corpus)
    {
        var failures = new List<string>();
        foreach (var @case in corpus.Cases)
        {
            var actual = EngineDispatcher.Run(@case.Engine, @case.Input);
            var actualSummary = Summary(@case.Engine, actual);
            var expectedSummary = CanonicalJson.Serialize(@case.ExpectedSummary);
            var actualSummaryJson = CanonicalJson.Serialize(actualSummary);
            var actualHash = CanonicalJson.Sha256(actual);
            if (!string.Equals(expectedSummary, actualSummaryJson, StringComparison.Ordinal)
                || !string.Equals(@case.ExpectedSha256, actualHash, StringComparison.OrdinalIgnoreCase))
            {
                failures.Add($"{@case.Id}: summary={actualSummaryJson}, hash={actualHash}");
            }
        }
        return new GoldenParityReport(
            corpus.Cases.Count,
            corpus.Cases.Count - failures.Count,
            failures.Count,
            failures,
            failures.Count == 0);
    }

    private static object Summary(string engine, object output) => engine switch
    {
        "calculate_change_risk" =>
            new Dictionary<string, object?>
            {
                ["overall_score"] = ((Dictionary<string, object?>)output)["overall_score"],
                ["level"] = ((Dictionary<string, object?>)output)["level"],
                ["data_quality"] = ((Dictionary<string, object?>)output)["data_quality"]
            },
        "calculate_blast_radius" =>
            new Dictionary<string, object?>
            {
                ["node_ids"] = ((IEnumerable<Dictionary<string, object?>>)((Dictionary<string, object?>)output)["nodes"]!)
                    .Select(item => item["id"])
                    .ToArray(),
                ["edge_count"] = ((IEnumerable<Dictionary<string, object?>>)((Dictionary<string, object?>)output)["edges"]!).Count(),
                ["max_hop"] = ((IEnumerable<Dictionary<string, object?>>)((Dictionary<string, object?>)output)["nodes"]!)
                    .Select(item => Convert.ToInt32(item["hop_distance"]))
                    .DefaultIfEmpty(0)
                    .Max()
            },
        "rank_hypotheses" =>
            new Dictionary<string, object?>
            {
                ["ranked_ids"] = ((IEnumerable<Dictionary<string, object?>>)output)
                    .Select(item => item["id"])
                    .ToArray(),
                ["scores"] = ((IEnumerable<Dictionary<string, object?>>)output)
                    .Select(item => item["score"])
                    .ToArray()
            },
        _ => throw new InvalidOperationException($"Unsupported summary engine: {engine}")
    };

    private static ContractParityReport VerifyContracts(string baseDirectory)
    {
        var differences = new List<string>();
        var store = new ReadOnlySpikeStore(baseDirectory);
        var contractPath = Path.Combine(baseDirectory, "contracts", "representative-responses.json");
        using var responseDocument = JsonDocument.Parse(File.ReadAllText(contractPath));
        using var openApiDocument = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(baseDirectory, "contracts", "openapi.json")));
        var openApiPaths = openApiDocument.RootElement.GetProperty("paths");
        var checkedRoutes = 0;
        var checkedResponses = 0;
        foreach (var response in responseDocument.RootElement.GetProperty("responses").EnumerateArray())
        {
            var concretePath = response.GetProperty("request").GetProperty("path").GetString()!;
            var path = TemplatePath(concretePath);
            var name = response.GetProperty("name").GetString()!;
            if (!openApiPaths.TryGetProperty(path, out var route)
                || !route.TryGetProperty("get", out _))
            {
                differences.Add($"Missing GET route in OpenAPI fixture: {path}");
                continue;
            }
            checkedRoutes++;
            var actual = store.ResponseByPath(concretePath);
            if (actual is null
                || !string.Equals(CanonicalJson.Serialize(response.GetProperty("body")),
                    CanonicalJson.Serialize(actual.Value), StringComparison.Ordinal))
            {
                differences.Add($"Representative response mismatch: {name}");
            }
            else
            {
                checkedResponses++;
            }
        }
        return new ContractParityReport(
            "representative-read-only-v1",
            checkedRoutes,
            checkedResponses,
            differences,
            differences.Count == 0);
    }

    private static string TemplatePath(string path) =>
        path.StartsWith("/api/v1/changes/", StringComparison.Ordinal)
            ? "/api/v1/changes/{change_id}"
            : path.StartsWith("/api/v1/incidents/", StringComparison.Ordinal)
                ? "/api/v1/incidents/{incident_id}"
                : path;

    private static BenchmarkReport Benchmark(GoldenCorpus corpus, int iterations)
    {
        iterations = Math.Max(1, iterations);
        for (var warmup = 0; warmup < 25; warmup++)
        {
            foreach (var @case in corpus.Cases)
                _ = EngineDispatcher.Run(@case.Engine, @case.Input);
        }

        var samples = new List<double>(iterations);
        for (var iteration = 0; iteration < iterations; iteration++)
        {
            var start = Stopwatch.GetTimestamp();
            foreach (var @case in corpus.Cases)
                _ = EngineDispatcher.Run(@case.Engine, @case.Input);
            samples.Add(Stopwatch.GetElapsedTime(start).TotalMicroseconds);
        }
        samples.Sort();
        var operations = iterations * corpus.Cases.Count;
        var elapsedSeconds = samples.Sum() / 1_000_000.0;
        return new BenchmarkReport(
            iterations,
            operations,
            Percentile(samples, 0.50),
            Percentile(samples, 0.95),
            Percentile(samples, 0.99),
            operations / elapsedSeconds,
            "all v1 golden cases per batch; in-process deterministic engines; no database or network");
    }

    private static double Percentile(IReadOnlyList<double> values, double percentile)
    {
        if (values.Count == 0) return 0;
        var index = (int)Math.Ceiling(percentile * values.Count) - 1;
        return values[Math.Clamp(index, 0, values.Count - 1)];
    }
}
