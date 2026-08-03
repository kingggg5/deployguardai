using System.Globalization;
using System.Text.Json;

namespace DeployGuard.ReadOnlySpike;

public static class EngineDispatcher
{
    public static object Run(string engine, JsonElement input) =>
        engine switch
        {
            "calculate_change_risk" => DeterministicEngines.CalculateChangeRisk(input),
            "calculate_blast_radius" => DeterministicEngines.CalculateBlastRadius(input),
            "rank_hypotheses" => DeterministicEngines.RankHypotheses(input),
            _ => throw new InvalidOperationException($"Unsupported golden engine: {engine}")
        };
}

public static class DeterministicEngines
{
    private const string AnalysisSchemaVersion = "1.0.0";
    private const string EngineVersion = "1.0.0";
    private const string RiskPolicyVersion = "risk-weighted-v1";
    private const string GraphVersion = "dependency-bfs-v1";
    private const string RcaPolicyVersion = "evidence-ranker-v1";

    private static readonly (string Key, double Weight)[] RiskWeights =
    [
        ("change_size", 0.25),
        ("service_scope", 0.20),
        ("change_type", 0.20),
        ("test_confidence", 0.15),
        ("operational_history", 0.10),
        ("safety_readiness", 0.10)
    ];

    private static readonly Dictionary<string, int> FlagRisk = new(StringComparer.Ordinal)
    {
        ["database-migration"] = 96,
        ["schema-change"] = 92,
        ["retry-policy"] = 90,
        ["auth-change"] = 86,
        ["api-contract"] = 78,
        ["config-change"] = 68,
        ["dependency-upgrade"] = 58,
        ["feature-flag"] = 42,
        ["docs-only"] = 8
    };

    private static readonly Dictionary<string, double> EvidenceReliability = new(StringComparer.OrdinalIgnoreCase)
    {
        ["trace"] = 1.00,
        ["metric"] = 0.95,
        ["deployment"] = 0.92,
        ["config"] = 0.90,
        ["log"] = 0.85,
        ["topology"] = 0.75,
        ["human"] = 0.72
    };

    public static Dictionary<string, object?> CalculateChangeRisk(JsonElement input)
    {
        var filesChanged = input.GetProperty("files_changed").GetInt32();
        var linesAdded = input.GetProperty("lines_added").GetInt32();
        var linesDeleted = input.GetProperty("lines_deleted").GetInt32();
        var services = Strings(input.GetProperty("changed_services"));
        var flags = Strings(input.GetProperty("flags"));
        var coverage = Clamp(input.GetProperty("test_coverage").GetDouble(), 0, 1);
        var rollbackReady = input.GetProperty("rollback_ready").GetBoolean();
        var observability = Clamp(input.GetProperty("observability_score").GetDouble(), 0, 1);
        var previousFailures = input.GetProperty("previous_failures").GetInt32();
        var serviceTiers = input.TryGetProperty("service_tiers", out var tiers)
            ? tiers.EnumerateObject().ToDictionary(item => item.Name, item => item.Value.ToString(), StringComparer.Ordinal)
            : new Dictionary<string, string>(StringComparer.Ordinal);
        var evidencePrefix = input.TryGetProperty("evidence_prefix", out var prefix)
            ? prefix.GetString() ?? "analysis"
            : "analysis";

        var totalLines = Math.Max(0, linesAdded) + Math.Max(0, linesDeleted);
        var sizeScore = RoundInt(Clamp(Math.Max(0, filesChanged) * 3 + totalLines / 12.0, 0, 100));
        var tierBonus = services.Select(service => TierBonus(serviceTiers.GetValueOrDefault(service))).DefaultIfEmpty(0).Max();
        var uniqueServices = services.Distinct(StringComparer.Ordinal).ToArray();
        var scopeScore = RoundInt(Clamp(
            uniqueServices.Length * 18 + Math.Max(0, uniqueServices.Length - 1) * 8 + tierBonus,
            0, 100));

        var normalizedFlags = flags.Select(item => item.ToLowerInvariant()).ToArray();
        var flagValues = normalizedFlags.Select(flag => FlagRisk.GetValueOrDefault(flag, 48)).ToArray();
        var typeScore = RoundInt(Clamp(
            (flagValues.Length == 0 ? 20 : flagValues.Max())
            + Math.Max(0, normalizedFlags.Distinct(StringComparer.Ordinal).Count() - 1) * 4,
            0, 100));
        var testScore = RoundInt((1 - coverage) * 100);
        var historyScore = RoundInt(Clamp(Math.Max(0, previousFailures) * 25, 0, 100));
        var safetyScore = RoundInt(Clamp(
            (rollbackReady ? 0 : 65) + (1 - observability) * 35,
            0, 100));

        var values = new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["change_size"] = sizeScore,
            ["service_scope"] = scopeScore,
            ["change_type"] = typeScore,
            ["test_confidence"] = testScore,
            ["operational_history"] = historyScore,
            ["safety_readiness"] = safetyScore
        };
        var labels = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["change_size"] = "Change size",
            ["service_scope"] = "Service scope",
            ["change_type"] = "Change type",
            ["test_confidence"] = "Test confidence gap",
            ["operational_history"] = "Operational history",
            ["safety_readiness"] = "Safety readiness gap"
        };
        var reasons = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["change_size"] = $"{filesChanged} files and {totalLines} changed lines increase review surface.",
            ["service_scope"] = $"{uniqueServices.Length} services are directly changed; criticality is included.",
            ["change_type"] = "Flags carry fixed risk priors: "
                + (normalizedFlags.Length == 0 ? "no elevated flags" : string.Join(", ", normalizedFlags)) + ".",
            ["test_confidence"] = $"Reported test coverage is {Percent0(coverage)}%.",
            ["operational_history"] = $"{Math.Max(0, previousFailures)} related previous failures were reported.",
            ["safety_readiness"] = $"Rollback readiness is {(rollbackReady ? "available" : "missing")}; observability is {Percent0(observability)}%."
        };
        var evidenceSuffixes = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["change_size"] = "diff",
            ["service_scope"] = "topology",
            ["change_type"] = "flags",
            ["test_confidence"] = "tests",
            ["operational_history"] = "history",
            ["safety_readiness"] = "readiness"
        };
        var dimensions = RiskWeights.Select(item => new Dictionary<string, object?>
        {
            ["key"] = item.Key,
            ["label"] = labels[item.Key],
            ["score"] = values[item.Key],
            ["weight"] = item.Weight,
            ["reason"] = reasons[item.Key],
            ["evidence_ids"] = new[] { $"{evidencePrefix}-{evidenceSuffixes[item.Key]}" }
        }).ToArray();

        var overallScore = RoundInt(Clamp(RiskWeights.Sum(item => values[item.Key] * item.Weight), 0, 100));
        var level = overallScore < 25 ? "low" : overallScore < 50 ? "moderate" : overallScore < 70 ? "high" : "critical";
        var recommendations = new List<string>();
        if (typeScore >= 70)
            recommendations.Add("Require an owner review for the elevated change type before deployment.");
        if (testScore >= 35)
            recommendations.Add("Add targeted tests for the changed paths before promoting the deployment.");
        if (scopeScore >= 60)
            recommendations.Add("Use a staged rollout and watch directly dependent services.");
        if (!rollbackReady)
            recommendations.Add("Prepare and verify a rollback procedure before deployment.");
        if (observability < 0.7)
            recommendations.Add("Add telemetry for the changed services before rollout.");
        if (recommendations.Count == 0)
            recommendations.Add("Proceed with the normal review path and monitor deployment guardrails.");

        var dataQuality = Round2(Clamp(0.55 + observability * 0.20 + coverage * 0.15 + (uniqueServices.Length > 0 ? 0.10 : 0), 0, 1));
        return new Dictionary<string, object?>
        {
            ["overall_score"] = overallScore,
            ["level"] = level,
            ["data_quality"] = dataQuality,
            ["dimensions"] = dimensions,
            ["recommendations"] = recommendations.ToArray()
        };
    }

    public static Dictionary<string, object?> CalculateBlastRadius(JsonElement input)
    {
        var nodes = new Dictionary<string, Node>(StringComparer.Ordinal);
        foreach (var item in input.GetProperty("nodes").EnumerateArray())
        {
            var node = Node.FromJson(item);
            nodes[node.Id] = node;
        }
        var changedServices = Strings(input.GetProperty("changed_services"));
        foreach (var serviceId in changedServices)
        {
            nodes.TryAdd(serviceId, new Node(serviceId, serviceId.Replace("-", " ", StringComparison.Ordinal).ToTitleCase(), "service", "Unassigned", "tier-3", "unknown"));
        }

        var adjacency = new Dictionary<string, List<Edge>>(StringComparer.Ordinal);
        foreach (var raw in input.GetProperty("edges").EnumerateArray())
        {
            var edge = Edge.FromJson(raw);
            if (!edge.Active) continue;
            if (!adjacency.TryGetValue(edge.Source, out var list))
            {
                list = [];
                adjacency[edge.Source] = list;
            }
            list.Add(edge);
        }
        foreach (var list in adjacency.Values)
            list.Sort((left, right) => string.CompareOrdinal(left.Target + "\u0000" + left.Relation, right.Target + "\u0000" + right.Relation));

        var distance = new Dictionary<string, int>(StringComparer.Ordinal);
        var pathConfidence = new Dictionary<string, double>(StringComparer.Ordinal);
        var origins = new Dictionary<string, string>(StringComparer.Ordinal);
        var queue = new Queue<string>();
        foreach (var serviceId in changedServices.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal))
        {
            distance[serviceId] = 0;
            pathConfidence[serviceId] = 1.0;
            origins[serviceId] = serviceId;
            queue.Enqueue(serviceId);
        }
        var maxHops = input.GetProperty("max_hops").GetInt32();
        var decay = input.GetProperty("decay").GetDouble();
        while (queue.Count > 0)
        {
            var source = queue.Dequeue();
            if (distance[source] >= maxHops) continue;
            if (!adjacency.TryGetValue(source, out var outgoing)) continue;
            foreach (var edge in outgoing)
            {
                if (!nodes.ContainsKey(edge.Target)) continue;
                var nextDistance = distance[source] + 1;
                var nextConfidence = pathConfidence[source] * Clamp(edge.Confidence, 0, 1);
                var better = !distance.ContainsKey(edge.Target)
                    || nextDistance < distance[edge.Target]
                    || (nextDistance == distance[edge.Target] && nextConfidence > pathConfidence[edge.Target]);
                if (!better) continue;
                distance[edge.Target] = nextDistance;
                pathConfidence[edge.Target] = nextConfidence;
                origins[edge.Target] = origins[source];
                queue.Enqueue(edge.Target);
            }
        }

        var resultNodes = distance
            .OrderBy(item => item.Value)
            .ThenBy(item => item.Key, StringComparer.Ordinal)
            .Select(item =>
            {
                var node = nodes[item.Key];
                var impact = item.Value == 0
                    ? 100
                    : RoundInt(Clamp(100 * Math.Pow(decay, item.Value)
                        * pathConfidence[item.Key]
                        * TierFactor(node.Tier)
                        * HealthFactor(node.Health), 0, 100));
                return new Dictionary<string, object?>
                {
                    ["id"] = item.Key,
                    ["label"] = node.Label,
                    ["kind"] = node.Kind,
                    ["team"] = node.Team,
                    ["tier"] = node.Tier,
                    ["health"] = node.Health,
                    ["impact_score"] = impact,
                    ["hop_distance"] = item.Value,
                    ["evidence_ids"] = new[] { $"{input.GetProperty("evidence_prefix").GetString()}-{origins[item.Key]}-{item.Key}" }
                };
            })
            .ToArray();

        var resultEdges = input.GetProperty("edges").EnumerateArray()
            .Select(Edge.FromJson)
            .Where(edge => edge.Active
                && distance.ContainsKey(edge.Source)
                && distance.ContainsKey(edge.Target)
                && distance[edge.Target] == distance[edge.Source] + 1)
            .Select(edge => new Dictionary<string, object?>
            {
                ["source"] = edge.Source,
                ["target"] = edge.Target,
                ["relation"] = edge.Relation,
                ["confidence"] = Round2(Clamp(edge.Confidence, 0, 1)),
                ["active"] = true
            })
            .OrderBy(edge => ((Dictionary<string, object?>)edge)["source"]?.ToString(), StringComparer.Ordinal)
            .ThenBy(edge => ((Dictionary<string, object?>)edge)["target"]?.ToString(), StringComparer.Ordinal)
            .ToArray();
        return new Dictionary<string, object?>
        {
            ["nodes"] = resultNodes,
            ["edges"] = resultEdges
        };
    }

    public static List<Dictionary<string, object?>> RankHypotheses(JsonElement input)
    {
        var evidence = input.GetProperty("evidence").EnumerateArray().Select(Evidence.FromJson).ToArray();
        var candidates = input.GetProperty("candidates").EnumerateArray().Select(Candidate.FromJson).ToArray();
        var limit = input.GetProperty("limit").GetInt32();
        var ranked = candidates.Select(candidate =>
        {
            var supporting = evidence.Where(item => item.Supports.Contains(candidate.Id, StringComparer.Ordinal)).ToArray();
            var contradicting = evidence.Where(item => item.Contradicts.Contains(candidate.Id, StringComparer.Ordinal)).ToArray();
            static double Strength(Evidence item) =>
                Clamp(item.Quality, 0, 1) * EvidenceReliability.GetValueOrDefault(item.Type, 0.70);
            var supportStrength = supporting.Sum(Strength);
            var counterStrength = contradicting.Sum(Strength);
            var distinctTypes = supporting.Select(item => item.Type).Distinct(StringComparer.Ordinal).Count();
            var prior = Clamp(candidate.Prior, 0, 1);
            var score = RoundInt(Clamp(
                prior * 25 + Math.Min(55, supportStrength * 16)
                - Math.Min(45, counterStrength * 28)
                + Math.Min(10, distinctTypes * 3)
                + Math.Min(6, supporting.Length * 1.5), 0, 100));
            var averageQuality = supporting.Length == 0 ? 0.0 : supporting.Average(item => item.Quality);
            var confidence = Round2(Clamp(
                0.15 + 0.55 * (score / 100.0)
                + 0.15 * Math.Min(1.0, supporting.Length / 2.0)
                + 0.10 * averageQuality
                - 0.12 * Math.Min(1.0, counterStrength), 0.05, 0.98));
            var reasoning = supporting.Length > 0
                ? $"{supporting.Length} evidence item(s) support this cause across {distinctTypes} evidence type(s)"
                : "No direct supporting evidence is currently available";
            reasoning += contradicting.Length > 0
                ? $"; {contradicting.Length} counter-evidence item(s) reduce confidence."
                : "; no counter-evidence is currently recorded.";
            return new RankedCandidate(candidate.Id, candidate.CauseService, candidate.Cause, confidence, score,
                supporting.Select(item => item.Id).ToArray(), contradicting.Select(item => item.Id).ToArray(),
                reasoning, candidate.NextStep, candidate.Status);
        }).OrderByDescending(item => item.Score).ThenBy(item => item.Id, StringComparer.Ordinal)
            .Take(Math.Max(0, limit)).ToArray();

        return ranked.Select((item, index) => new Dictionary<string, object?>
            {
                ["id"] = item.Id,
                ["rank"] = index + 1,
                ["cause_service"] = item.CauseService,
                ["cause"] = item.Cause,
                ["confidence"] = item.Confidence,
                ["score"] = item.Score,
                ["evidence_ids"] = item.EvidenceIds,
                ["counter_evidence_ids"] = item.CounterEvidenceIds,
                ["reasoning"] = item.Reasoning,
                ["next_step"] = item.NextStep,
                ["status"] = item.Status
            }).ToList();
    }

    private static int TierBonus(string? value) => TierNumber(value) switch
    {
        1 => 25,
        2 => 12,
        3 => 4,
        _ => 4
    };

    private static double TierFactor(string value) => TierNumber(value) switch
    {
        1 => 1.0,
        2 => 0.92,
        3 => 0.82,
        _ => 0.82
    };

    private static double HealthFactor(string value) => value.ToLowerInvariant() switch
    {
        "critical" => 1.20,
        "degraded" => 1.10,
        "healthy" => 1.00,
        _ => 0.90
    };

    private static int TierNumber(string? value)
    {
        var text = (value ?? "").ToLowerInvariant().Replace("tier", "", StringComparison.Ordinal).Trim(' ', '-', '_');
        return int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var result) ? result : 3;
    }

    private static string[] Strings(JsonElement value) => value.EnumerateArray().Select(item => item.GetString() ?? "").ToArray();
    private static double Clamp(double value, double minimum, double maximum) => Math.Max(minimum, Math.Min(maximum, value));
    private static int RoundInt(double value) => (int)Math.Round(value, MidpointRounding.ToEven);
    private static double Round2(double value) => Math.Round(
        value + (value >= 0 ? 1e-12 : -1e-12), 2, MidpointRounding.ToEven);
    private static string Percent0(double value) =>
        Math.Round(value * 100, MidpointRounding.ToEven).ToString("0", CultureInfo.InvariantCulture);

    private sealed record Node(string Id, string Label, string Kind, string Team, string Tier, string Health)
    {
        public static Node FromJson(JsonElement value) => new(
            value.GetProperty("id").GetString()!,
            value.GetProperty("label").GetString()!,
            value.GetProperty("kind").GetString()!,
            value.GetProperty("team").GetString()!,
            value.GetProperty("tier").GetString()!,
            value.GetProperty("health").GetString()!);
    }

    private sealed record Edge(string Source, string Target, string Relation, double Confidence, bool Active)
    {
        public static Edge FromJson(JsonElement value) => new(
            value.GetProperty("source").GetString()!,
            value.GetProperty("target").GetString()!,
            value.TryGetProperty("relation", out var relation) ? relation.GetString() ?? "runtime-dependency" : "runtime-dependency",
            value.TryGetProperty("confidence", out var confidence) ? confidence.GetDouble() : 1.0,
            !value.TryGetProperty("active", out var active) || active.GetBoolean());
    }

    private sealed record Evidence(string Id, string Type, double Quality, string[] Supports, string[] Contradicts)
    {
        public static Evidence FromJson(JsonElement value) => new(
            value.GetProperty("id").GetString()!,
            value.GetProperty("type").GetString() ?? "",
            value.TryGetProperty("quality", out var quality) ? quality.GetDouble() : 0.5,
            value.TryGetProperty("supports", out var supports) ? Strings(supports) : [],
            value.TryGetProperty("contradicts", out var contradicts) ? Strings(contradicts) : []);
    }

    private sealed record Candidate(string Id, string CauseService, string Cause, double Prior, string NextStep, string Status)
    {
        public static Candidate FromJson(JsonElement value) => new(
            value.GetProperty("id").GetString()!,
            value.GetProperty("cause_service").GetString()!,
            value.GetProperty("cause").GetString()!,
            value.TryGetProperty("prior", out var prior) ? prior.GetDouble() : 0.5,
            value.GetProperty("next_step").GetString()!,
            value.TryGetProperty("status", out var status) ? status.GetString() ?? "unreviewed" : "unreviewed");
    }

    private sealed record RankedCandidate(string Id, string CauseService, string Cause, double Confidence, int Score,
        string[] EvidenceIds, string[] CounterEvidenceIds, string Reasoning, string NextStep, string Status);
}

internal static class TitleCaseExtensions
{
    public static string ToTitleCase(this string value) => string.Join(' ', value.Split(' ', StringSplitOptions.RemoveEmptyEntries)
        .Select(item => item.Length == 0 ? item : char.ToUpperInvariant(item[0]) + item[1..]));
}
