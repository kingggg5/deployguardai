namespace DeployGuard.ControlPlane.Contracts;

public sealed record RootResponse(
	string Service,
	string Status,
	string DataMode,
	bool UpstreamConfigured);

public sealed record LivenessResponse(string Status, string Service);

public sealed record HealthResponse(
	string Status,
	string Database,
	string Service,
	string DataMode);

public sealed record ErrorResponse(string Detail, string Code);

public sealed record ReadinessErrorResponse(
	string Detail,
	string Code,
	IReadOnlyDictionary<string, string> Checks);
