using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.TestHost;

namespace DeployGuard.ControlPlane.Tests;

internal sealed class ControlPlaneFactory(
	string upstreamBaseUrl,
	Action<IServiceCollection>? configureServices = null,
	IReadOnlyDictionary<string, string?>? configurationOverrides = null,
	IPAddress? remoteIpAddress = null)
	: WebApplicationFactory<Program>
{
	protected override void ConfigureWebHost(IWebHostBuilder builder)
	{
		builder.ConfigureAppConfiguration((_, configuration) =>
		{
			var values = new Dictionary<string, string?>
				{
					["Upstream:BaseUrl"] = upstreamBaseUrl,
					["Upstream:ReadinessPath"] = "/api/v1/health/ready",
					["Upstream:TimeoutSeconds"] = "1",
					["Database:ProbeEnabled"] = "false",
					["DataMode"] = "connected"
				};
			foreach (var (key, value) in configurationOverrides
				?? new Dictionary<string, string?>())
			{
				values[key] = value;
			}
			configuration.AddInMemoryCollection(values);
		});
		if (remoteIpAddress is not null)
		{
			builder.ConfigureServices(services =>
				services.AddSingleton<IStartupFilter>(
					new RemoteIpAddressStartupFilter(remoteIpAddress)));
		}
		if (configureServices is not null)
		{
			builder.ConfigureTestServices(configureServices);
		}
	}

	private sealed class RemoteIpAddressStartupFilter(
		IPAddress remoteIpAddress) : IStartupFilter
	{
		public Action<IApplicationBuilder> Configure(
			Action<IApplicationBuilder> next) =>
			application =>
			{
				application.Use(async (context, continuation) =>
				{
					context.Connection.RemoteIpAddress = remoteIpAddress;
					await continuation(context);
				});
				next(application);
			};
	}
}
