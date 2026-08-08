using DeployGuard.ControlPlane.Configuration;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Primitives;
using Yarp.ReverseProxy.Configuration;
using Yarp.ReverseProxy.Forwarder;

namespace DeployGuard.ControlPlane.Proxy;

public sealed class ControlPlaneProxyConfigProvider : IProxyConfigProvider
{
	private readonly IProxyConfig _config;

	public ControlPlaneProxyConfigProvider(IOptions<UpstreamOptions> options)
	{
		_config = BuildConfig(options.Value);
	}

	public IProxyConfig GetConfig() => _config;

	private static IProxyConfig BuildConfig(UpstreamOptions options)
	{
		if (!options.TryGetBaseUri(out var baseUri) || baseUri is null)
		{
			return new StaticProxyConfig([], []);
		}

		var routes = new[]
		{
			new RouteConfig
			{
				RouteId = "python-api-fallback",
				ClusterId = "python-api",
				Order = 10_000,
				Match = new RouteMatch { Path = "/{**catch-all}" },
				Transforms = new List<IReadOnlyDictionary<string, string>>
				{
					new Dictionary<string, string>
					{
						["ResponseHeaderRemove"] = "Server"
					}
				}
			}
		};
		var clusters = new[]
		{
			new ClusterConfig
			{
				ClusterId = "python-api",
				HttpRequest = new ForwarderRequestConfig
				{
					ActivityTimeout = TimeSpan.FromSeconds(30)
				},
				Destinations = new Dictionary<string, DestinationConfig>(
					StringComparer.OrdinalIgnoreCase)
				{
					["python-api-primary"] = new DestinationConfig
					{
						Address = baseUri.AbsoluteUri
					}
				}
			}
		};
		return new StaticProxyConfig(routes, clusters);
	}

	private sealed class StaticProxyConfig(
		IReadOnlyList<RouteConfig> routes,
		IReadOnlyList<ClusterConfig> clusters) : IProxyConfig
	{
		public IReadOnlyList<RouteConfig> Routes { get; } = routes;
		public IReadOnlyList<ClusterConfig> Clusters { get; } = clusters;
		public IChangeToken ChangeToken { get; } =
			new CancellationChangeToken(CancellationToken.None);
	}
}
