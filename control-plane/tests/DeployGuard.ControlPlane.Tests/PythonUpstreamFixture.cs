using System.Collections.Concurrent;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;

namespace DeployGuard.ControlPlane.Tests;

public sealed class PythonUpstreamFixture : IAsyncLifetime
{
	private WebApplication? _application;

	public string BaseAddress { get; private set; } = string.Empty;
	public ConcurrentDictionary<string, string> RequestIds { get; } = new();
	public ConcurrentDictionary<string, string> ForwardedFors { get; } = new();
	public ConcurrentDictionary<string, string> ForwardedProtos { get; } = new();

	public async Task InitializeAsync()
	{
		var builder = WebApplication.CreateSlimBuilder();
		builder.WebHost.UseKestrel().UseUrls("http://127.0.0.1:0");
		_application = builder.Build();
		_application.MapGet(
			"/api/v1/health/ready",
			() => Results.Json(new
			{
				status = "ok",
				database = "ready",
				service = "deployguard-ai",
				data_mode = "connected"
			}));
		_application.Map(
			"/{**catchAll}",
			async context =>
			{
				RequestIds[context.Request.Path.Value ?? "/"] =
					context.Request.Headers["X-Request-ID"].ToString();
				ForwardedFors[context.Request.Path.Value ?? "/"] =
					context.Request.Headers["X-Forwarded-For"].ToString();
				ForwardedProtos[context.Request.Path.Value ?? "/"] =
					context.Request.Headers["X-Forwarded-Proto"].ToString();
				context.Response.Headers.Server = "python-test-upstream";
				await context.Response.WriteAsJsonAsync(new
				{
					proxied = true,
					path = context.Request.Path.Value
				});
			});
		await _application.StartAsync();
		var addresses = _application.Services
			.GetRequiredService<IServer>()
			.Features
			.Get<IServerAddressesFeature>()
			?.Addresses;
		BaseAddress = addresses?.Single()
			?? throw new InvalidOperationException("Upstream address was not assigned");
	}

	public async Task DisposeAsync()
	{
		if (_application is not null)
		{
			await _application.DisposeAsync();
		}
	}
}
