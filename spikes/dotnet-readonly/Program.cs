using DeployGuard.ReadOnlySpike;

if (args.Contains("--verify", StringComparer.OrdinalIgnoreCase))
{
    var output = ArgumentValue(args, "--output");
    var iterations = PositiveIntArgument(args, "--iterations", 1_000);
    var report = await SpikeVerifier.RunAsync(AppContext.BaseDirectory, iterations);
    var json = CanonicalJson.Serialize(report);
    if (output is not null)
    {
        var outputPath = ResolveRepositoryPath(output, AppContext.BaseDirectory);
        Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
        await File.WriteAllTextAsync(outputPath, json + Environment.NewLine);
    }

    Console.WriteLine(json);
    Environment.ExitCode = report.Passed ? 0 : 1;
    return;
}

var caseArgument = ArgumentValue(args, "--case");
if (caseArgument is not null)
{
    var corpus = GoldenCorpus.Load(AppContext.BaseDirectory);
    var @case = corpus.Cases.Single(item =>
        string.Equals(item.Id, caseArgument, StringComparison.Ordinal));
    Console.WriteLine(CanonicalJson.Serialize(EngineDispatcher.Run(@case.Engine, @case.Input)));
    return;
}

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton(new ReadOnlySpikeStore(AppContext.BaseDirectory));
var app = builder.Build();

app.MapGet("/", () => Results.Json(new
{
    service = "deployguard-dotnet-readonly-spike",
    mode = "read-only",
    data_mode = "synthetic",
    warning = "This spike is not a production authority and has no write endpoints."
}));

app.MapGet("/api/v1/health/live", () => Results.Json(new
{
    status = "ok",
    service = "deployguard-ai",
    data_mode = "synthetic"
}));

app.MapGet("/api/v1/health/ready", () => Results.Json(new
{
    status = "ok",
    service = "deployguard-ai",
    database = "fixture-only",
    data_mode = "synthetic"
}));

app.MapGet("/api/v1/spike/report", async () =>
    Results.Json(await SpikeVerifier.RunAsync(AppContext.BaseDirectory)));

app.MapGet("/api/v1/spike/golden/{caseId}", (string caseId) =>
{
    var corpus = GoldenCorpus.Load(AppContext.BaseDirectory);
    var @case = corpus.Cases.FirstOrDefault(item =>
        string.Equals(item.Id, caseId, StringComparison.Ordinal));
    return @case is null
        ? Results.NotFound(new { detail = "Unknown golden case", case_id = caseId })
        : Results.Json(EngineDispatcher.Run(@case.Engine, @case.Input));
});

app.MapGet("/api/v1/health", (ReadOnlySpikeStore store) =>
    Results.Json(store.Response("health")));

app.MapGet("/api/v1/overview", (ReadOnlySpikeStore store) =>
    Results.Json(store.Response("overview")));

app.MapGet("/api/v1/changes/{changeId}", (string changeId, ReadOnlySpikeStore store) =>
{
    var response = store.ResponseByPath($"/api/v1/changes/{changeId}");
    return response is null
        ? Results.NotFound(new { detail = "Change not found", change_id = changeId })
        : Results.Json(response);
});

app.MapGet("/api/v1/incidents/{incidentId}", (string incidentId, ReadOnlySpikeStore store) =>
{
    var response = store.ResponseByPath($"/api/v1/incidents/{incidentId}");
    return response is null
        ? Results.NotFound(new { detail = "Incident not found", incident_id = incidentId })
        : Results.Json(response);
});

app.Run();

static string? ArgumentValue(string[] args, string name)
{
    var index = Array.FindIndex(args, item =>
        string.Equals(item, name, StringComparison.OrdinalIgnoreCase));
    return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
}

static int PositiveIntArgument(string[] args, string name, int fallback)
{
    var value = ArgumentValue(args, name);
    return int.TryParse(value, out var parsed) && parsed > 0 ? parsed : fallback;
}

static string ResolveRepositoryPath(string path, string baseDirectory)
{
    if (Path.IsPathRooted(path)) return path;
    var directory = new DirectoryInfo(baseDirectory);
    while (directory is not null)
    {
        if (File.Exists(Path.Combine(directory.FullName, "scripts", "evaluation", "golden-corpus-v1.json")))
            return Path.Combine(directory.FullName, path);
        directory = directory.Parent;
    }
    return Path.GetFullPath(path);
}
