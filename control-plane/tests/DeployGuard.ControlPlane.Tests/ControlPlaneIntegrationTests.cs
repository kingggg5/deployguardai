using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using DeployGuard.ControlPlane.Readiness;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace DeployGuard.ControlPlane.Tests;

public sealed class ControlPlaneIntegrationTests(
	PythonUpstreamFixture upstream) : IClassFixture<PythonUpstreamFixture>
{
	[Fact]
	public async Task Native_health_contracts_match_fastapi_success_shape()
	{
		await using var factory = new ControlPlaneFactory(upstream.BaseAddress);
		using var client = factory.CreateClient();

		using var live = await client.GetAsync("/api/v1/health/live");
		Assert.Equal(HttpStatusCode.OK, live.StatusCode);
		using var liveBody = JsonDocument.Parse(await live.Content.ReadAsStringAsync());
		Assert.Equal("ok", liveBody.RootElement.GetProperty("status").GetString());
		Assert.Equal(
			"DeployGuard AI",
			liveBody.RootElement.GetProperty("service").GetString());

		foreach (var path in new[] { "/api/v1/health", "/api/v1/health/ready" })
		{
			using var ready = await client.GetAsync(path);
			Assert.Equal(HttpStatusCode.OK, ready.StatusCode);
			using var readyBody = JsonDocument.Parse(await ready.Content.ReadAsStringAsync());
			Assert.Equal("ok", readyBody.RootElement.GetProperty("status").GetString());
			Assert.Equal("ready", readyBody.RootElement.GetProperty("database").GetString());
			Assert.Equal(
				"deployguard-ai",
				readyBody.RootElement.GetProperty("service").GetString());
			Assert.Equal(
				"connected",
				readyBody.RootElement.GetProperty("data_mode").GetString());
		}
	}

	[Fact]
	public async Task Root_is_native_and_uses_snake_case_json()
	{
		await using var factory = new ControlPlaneFactory(upstream.BaseAddress);
		using var client = factory.CreateClient();

		using var response = await client.GetAsync("/");
		response.EnsureSuccessStatusCode();
		using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync());

		Assert.Equal(
			"deployguard-control-plane",
			body.RootElement.GetProperty("service").GetString());
		Assert.True(body.RootElement.GetProperty("upstream_configured").GetBoolean());
		Assert.False(upstream.RequestIds.ContainsKey("/"));
	}

	[Fact]
	public async Task Valid_request_id_is_preserved_and_forwarded()
	{
		await using var factory = new ControlPlaneFactory(upstream.BaseAddress);
		using var client = factory.CreateClient();
		const string requestId = "request_ABC-123.trace";
		using var request = new HttpRequestMessage(
			HttpMethod.Get,
			"/api/v1/capabilities");
		request.Headers.TryAddWithoutValidation("X-Request-ID", requestId);

		using var response = await client.SendAsync(request);
		response.EnsureSuccessStatusCode();

		Assert.Equal(requestId, response.Headers.GetValues("X-Request-ID").Single());
		Assert.Equal(
			"dotnet-10",
			response.Headers.GetValues("X-DeployGuard-Control-Plane").Single());
		Assert.Equal(requestId, upstream.RequestIds["/api/v1/capabilities"]);
		Assert.False(response.Headers.Contains("Server"));
	}

	[Fact]
	public async Task Invalid_request_id_is_replaced_before_forwarding()
	{
		await using var factory = new ControlPlaneFactory(upstream.BaseAddress);
		using var client = factory.CreateClient();
		using var request = new HttpRequestMessage(
			HttpMethod.Get,
			"/api/v1/capabilities-invalid-id");
		request.Headers.TryAddWithoutValidation("X-Request-ID", "invalid id/value");

		using var response = await client.SendAsync(request);
		response.EnsureSuccessStatusCode();
		var requestId = response.Headers.GetValues("X-Request-ID").Single();

		Assert.True(Guid.TryParse(requestId, out _));
		Assert.Equal(
			requestId,
			upstream.RequestIds["/api/v1/capabilities-invalid-id"]);
	}

	[Fact]
	public async Task Untrusted_forwarding_headers_are_ignored_and_overwritten()
	{
		const string path = "/api/v1/untrusted-forwarding";
		await using var factory = new ControlPlaneFactory(
			upstream.BaseAddress,
			remoteIpAddress: IPAddress.Parse("10.10.0.25"));
		using var client = factory.CreateClient();
		using var request = new HttpRequestMessage(HttpMethod.Get, path);
		request.Headers.TryAddWithoutValidation("X-Forwarded-For", "198.51.100.99");
		request.Headers.TryAddWithoutValidation("X-Forwarded-Proto", "https");

		using var response = await client.SendAsync(request);
		response.EnsureSuccessStatusCode();

		Assert.Equal("10.10.0.25", upstream.ForwardedFors[path]);
		Assert.Equal("http", upstream.ForwardedProtos[path]);
	}

	[Fact]
	public async Task Trusted_proxy_headers_are_resolved_once_then_overwritten()
	{
		const string path = "/api/v1/trusted-forwarding";
		var configuration = new Dictionary<string, string?>
		{
			["ForwardedHeaders:TrustedProxyCidrs:0"] = "10.10.0.0/24"
		};
		await using var factory = new ControlPlaneFactory(
			upstream.BaseAddress,
			configurationOverrides: configuration,
			remoteIpAddress: IPAddress.Parse("10.10.0.25"));
		var forwardedOptions = factory.Services
			.GetRequiredService<Microsoft.Extensions.Options.IOptions<
				Microsoft.AspNetCore.Builder.ForwardedHeadersOptions>>()
			.Value;
		Assert.Contains(
			forwardedOptions.KnownIPNetworks,
			network => network.Contains(IPAddress.Parse("10.10.0.25")));
		using var client = factory.CreateClient();
		using var request = new HttpRequestMessage(HttpMethod.Get, path);
		request.Headers.TryAddWithoutValidation(
			"X-Forwarded-For",
			"192.0.2.123, 198.51.100.42");
		request.Headers.TryAddWithoutValidation(
			"X-Forwarded-Proto",
			"http, https");

		using var response = await client.SendAsync(request);
		response.EnsureSuccessStatusCode();

		Assert.Equal("198.51.100.42", upstream.ForwardedFors[path]);
		Assert.Equal("https", upstream.ForwardedProtos[path]);
	}

	[Fact]
	public async Task Public_metrics_path_is_native_not_found_and_never_proxied()
	{
		const string path = "/api/v1/metrics";
		await using var factory = new ControlPlaneFactory(upstream.BaseAddress);
		using var client = factory.CreateClient();

		using var response = await client.GetAsync(path);

		Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
		Assert.False(upstream.RequestIds.ContainsKey(path));
		Assert.Equal(
			"dotnet-10",
			response.Headers.GetValues("X-DeployGuard-Control-Plane").Single());
	}

	[Fact]
	public async Task Missing_upstream_configuration_fails_closed()
	{
		await using var factory = new ControlPlaneFactory(string.Empty);
		using var client = factory.CreateClient();

		using var response = await client.GetAsync("/api/v1/capabilities");
		Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
		var body = await response.Content.ReadFromJsonAsync<JsonElement>();
		Assert.Equal(
			"upstream_not_configured",
			body.GetProperty("code").GetString());
	}

	[Fact]
	public async Task Readiness_and_proxy_fail_closed_when_upstream_is_unavailable()
	{
		await using var factory = new ControlPlaneFactory("http://127.0.0.1:1");
		using var client = factory.CreateClient();

		using var live = await client.GetAsync("/api/v1/health/live");
		Assert.Equal(HttpStatusCode.OK, live.StatusCode);

		using var ready = await client.GetAsync("/api/v1/health/ready");
		Assert.Equal(HttpStatusCode.ServiceUnavailable, ready.StatusCode);
		var readyBody = await ready.Content.ReadFromJsonAsync<JsonElement>();
		Assert.Equal(
			"control_plane_not_ready",
			readyBody.GetProperty("code").GetString());
		Assert.Equal(
			"unavailable",
			readyBody.GetProperty("checks").GetProperty("upstream").GetString());

		using var proxied = await client.GetAsync("/api/v1/capabilities");
		Assert.Equal(HttpStatusCode.ServiceUnavailable, proxied.StatusCode);
		var proxyBody = await proxied.Content.ReadFromJsonAsync<JsonElement>();
		Assert.Equal(
			"upstream_unavailable",
			proxyBody.GetProperty("code").GetString());
	}

	[Fact]
	public async Task Unhandled_errors_use_the_stable_envelope_without_details()
	{
		await using var factory = new ControlPlaneFactory(
			upstream.BaseAddress,
			services =>
			{
				services.RemoveAll<IControlPlaneReadiness>();
				services.AddSingleton<IControlPlaneReadiness, ThrowingReadiness>();
			});
		using var client = factory.CreateClient();

		using var response = await client.GetAsync("/api/v1/health/ready");
		Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
		var rawBody = await response.Content.ReadAsStringAsync();
		using var body = JsonDocument.Parse(rawBody);

		Assert.Equal("internal_error", body.RootElement.GetProperty("code").GetString());
		Assert.Equal(
			"Internal server error",
			body.RootElement.GetProperty("detail").GetString());
		Assert.DoesNotContain("sensitive failure detail", rawBody, StringComparison.Ordinal);
		Assert.True(response.Headers.Contains("X-Request-ID"));
	}

	private sealed class ThrowingReadiness : IControlPlaneReadiness
	{
		public Task<ReadinessSnapshot> CheckAsync(CancellationToken cancellationToken) =>
			throw new InvalidOperationException("sensitive failure detail");
	}
}
