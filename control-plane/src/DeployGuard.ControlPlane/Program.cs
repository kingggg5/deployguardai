using System.Text.Json;
using DeployGuard.ControlPlane;
using DeployGuard.ControlPlane.Configuration;
using DeployGuard.ControlPlane.Contracts;
using DeployGuard.ControlPlane.Proxy;
using DeployGuard.ControlPlane.Readiness;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.Options;
using Npgsql;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Yarp.ReverseProxy.Configuration;
using Yarp.ReverseProxy.Transforms;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.ConfigureKestrel(options => options.AddServerHeader = false);
builder.Services.ConfigureHttpJsonOptions(options =>
{
	options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
	options.SerializerOptions.DictionaryKeyPolicy = JsonNamingPolicy.SnakeCaseLower;
});
builder.Services
	.AddOptions<UpstreamOptions>()
	.Bind(builder.Configuration.GetSection(UpstreamOptions.SectionName))
	.Validate(
		options => options.TimeoutSeconds is >= 1 and <= 30,
		"Upstream:TimeoutSeconds must be between 1 and 30 seconds")
	.Validate(
		options => options.HasValidReadinessPath(),
		"Upstream:ReadinessPath must be a same-origin absolute path")
	.ValidateOnStart();
builder.Services
	.AddOptions<DatabaseOptions>()
	.Bind(builder.Configuration.GetSection(DatabaseOptions.SectionName));

builder.Services
	.AddOptions<ForwardedHeadersTrustOptions>()
	.Bind(builder.Configuration.GetSection(ForwardedHeadersTrustOptions.SectionName))
	.Validate(
		options => options.TryGetTrustedProxyNetworks(out _),
		"ForwardedHeaders:TrustedProxyCidrs must contain one or more valid CIDR networks")
	.ValidateOnStart();
builder.Services
	.AddOptions<ForwardedHeadersOptions>()
	.Configure<IOptions<ForwardedHeadersTrustOptions>>((options, trusted) =>
	{
		if (!trusted.Value.TryGetTrustedProxyNetworks(out var trustedProxyNetworks))
		{
			return;
		}

		options.ForwardedHeaders = ForwardedHeaders.XForwardedFor
			| ForwardedHeaders.XForwardedProto;
		options.ForwardLimit = 1;
		options.RequireHeaderSymmetry = true;
		options.KnownProxies.Clear();
		options.KnownIPNetworks.Clear();
		foreach (var network in trustedProxyNetworks)
		{
			options.KnownIPNetworks.Add(network);
		}
	});

var otlpEndpointValue = builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"]?.Trim();
Uri? otlpEndpoint = null;
if (!string.IsNullOrEmpty(otlpEndpointValue)
	&& (!Uri.TryCreate(otlpEndpointValue, UriKind.Absolute, out otlpEndpoint)
		|| (otlpEndpoint.Scheme != Uri.UriSchemeHttp
			&& otlpEndpoint.Scheme != Uri.UriSchemeHttps)
		|| !string.IsNullOrEmpty(otlpEndpoint.UserInfo)))
{
	throw new InvalidOperationException(
		"OTEL_EXPORTER_OTLP_ENDPOINT must be an absolute HTTP(S) URI without user information");
}
var telemetryServiceName = builder.Configuration["OTEL_SERVICE_NAME"]?.Trim();
if (string.IsNullOrEmpty(telemetryServiceName))
{
	telemetryServiceName = "deployguard-control-plane";
}

builder.Services
	.AddOpenTelemetry()
	.ConfigureResource(resource => resource.AddService(telemetryServiceName))
	.WithTracing(tracing =>
	{
		tracing
			.AddAspNetCoreInstrumentation()
			.AddHttpClientInstrumentation();
		if (otlpEndpoint is not null)
		{
			tracing.AddOtlpExporter(options => options.Endpoint = otlpEndpoint);
		}
	})
	.WithMetrics(metrics =>
	{
		metrics
			.AddAspNetCoreInstrumentation()
			.AddHttpClientInstrumentation()
			.AddRuntimeInstrumentation();
		if (otlpEndpoint is not null)
		{
			metrics.AddOtlpExporter(options => options.Endpoint = otlpEndpoint);
		}
	});

var dataMode = builder.Configuration["DataMode"]?.Trim().ToLowerInvariant()
	?? "connected";
if (dataMode is not ("synthetic" or "connected"))
{
	throw new InvalidOperationException(
		"DataMode must be either 'synthetic' or 'connected'");
}

var databaseProbeEnabled = builder.Configuration.GetValue<bool>(
	"Database:ProbeEnabled");
if (databaseProbeEnabled)
{
	var connectionString = builder.Configuration.GetConnectionString("DeployGuard");
	if (string.IsNullOrWhiteSpace(connectionString))
	{
		throw new InvalidOperationException(
			"ConnectionStrings:DeployGuard is required when Database:ProbeEnabled is true");
	}

	builder.Services.AddSingleton(_ => NpgsqlDataSource.Create(connectionString));
}

builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddHttpClient(
	"python-readiness",
	(services, client) =>
	{
		var options = services.GetRequiredService<IOptions<UpstreamOptions>>().Value;
		client.Timeout = TimeSpan.FromSeconds(options.TimeoutSeconds);
	});
builder.Services.AddSingleton<IUpstreamReadinessProbe, UpstreamReadinessProbe>();
builder.Services.AddSingleton<IDatabaseReadinessProbe, DatabaseReadinessProbe>();
builder.Services.AddSingleton<IControlPlaneReadiness, ControlPlaneReadiness>();
builder.Services.AddSingleton<IProxyConfigProvider, ControlPlaneProxyConfigProvider>();
builder.Services
	.AddReverseProxy()
	.AddTransforms(transformBuilderContext =>
	{
		transformBuilderContext.AddXForwarded(ForwardedTransformActions.Set);
		transformBuilderContext.AddRequestTransform(transformContext =>
		{
			var requestId = transformContext.HttpContext.TraceIdentifier;
			transformContext.ProxyRequest.Headers.Remove(RequestIdMiddleware.HeaderName);
			transformContext.ProxyRequest.Headers.TryAddWithoutValidation(
				RequestIdMiddleware.HeaderName,
				requestId);
			return ValueTask.CompletedTask;
		});
		transformBuilderContext.AddResponseTransform(transformContext =>
		{
			transformContext.HttpContext.Response.Headers.Remove("Server");
			return ValueTask.CompletedTask;
		});
	});

var app = builder.Build();
app.UseForwardedHeaders();
app.UseMiddleware<RequestIdMiddleware>();
app.UseMiddleware<RequestCompletionLoggingMiddleware>();
app.UseMiddleware<ExceptionHandlingMiddleware>();
app.Use(async (context, next) =>
{
	if (string.Equals(
			context.Request.Path.Value,
			"/api/v1/metrics",
			StringComparison.OrdinalIgnoreCase))
	{
		context.Response.StatusCode = StatusCodes.Status404NotFound;
		return;
	}

	await next(context);
});

app.MapGet(
	"/",
	(IOptions<UpstreamOptions> upstream) =>
	{
		var configured = upstream.Value.TryGetBaseUri(out _);
		return TypedResults.Ok(
			new RootResponse(
				"deployguard-control-plane",
				"ok",
				dataMode,
				configured));
	});

app.MapGet(
	"/api/v1/health/live",
	() => TypedResults.Ok(new LivenessResponse("ok", "DeployGuard AI")));

app.MapGet("/api/v1/health", HealthAsync);
app.MapGet("/api/v1/health/ready", HealthAsync);

app.MapReverseProxy(proxyPipeline =>
{
	proxyPipeline.Use(async (context, next) =>
	{
		var upstream = context.RequestServices
			.GetRequiredService<IUpstreamReadinessProbe>();
		if (!await upstream.IsReadyAsync(context.RequestAborted))
		{
			await WriteErrorAsync(
				context,
				"Python upstream is unavailable",
				"upstream_unavailable");
			return;
		}

		await next();
	});
});

app.MapFallback(context => WriteErrorAsync(
	context,
	"Python upstream is not configured",
	"upstream_not_configured"));

app.Run();

async Task<IResult> HealthAsync(
	IControlPlaneReadiness readiness,
	CancellationToken cancellationToken)
{
	var snapshot = await readiness.CheckAsync(cancellationToken);
	if (!snapshot.Ready)
	{
		return Results.Json(
			new ReadinessErrorResponse(
				"Control plane is not ready",
				"control_plane_not_ready",
				new Dictionary<string, string>
				{
					["upstream"] = snapshot.UpstreamStatus,
					["database"] = snapshot.DatabaseStatus
				}),
			statusCode: StatusCodes.Status503ServiceUnavailable);
	}

	return TypedResults.Ok(
		new HealthResponse("ok", "ready", "deployguard-ai", dataMode));
}

static async Task WriteErrorAsync(
	HttpContext context,
	string detail,
	string code)
{
	context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
	await context.Response.WriteAsJsonAsync(
		new ErrorResponse(detail, code),
		cancellationToken: context.RequestAborted);
}

public partial class Program;
