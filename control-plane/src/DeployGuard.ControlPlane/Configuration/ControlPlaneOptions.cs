using System.Net;

namespace DeployGuard.ControlPlane.Configuration;

public sealed class UpstreamOptions
{
	public const string SectionName = "Upstream";

	public string BaseUrl { get; init; } = string.Empty;
	public string ReadinessPath { get; init; } = "/api/v1/health/ready";
	public int TimeoutSeconds { get; init; } = 3;

	public bool TryGetBaseUri(out Uri? baseUri)
	{
		baseUri = null;
		if (!Uri.TryCreate(BaseUrl.Trim(), UriKind.Absolute, out var candidate)
			|| (!string.Equals(candidate.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
				&& !string.Equals(candidate.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
			|| !string.IsNullOrEmpty(candidate.UserInfo)
			|| !string.IsNullOrEmpty(candidate.Query)
			|| !string.IsNullOrEmpty(candidate.Fragment))
		{
			return false;
		}

		var builder = new UriBuilder(candidate)
		{
			Path = candidate.AbsolutePath.TrimEnd('/') + "/"
		};
		baseUri = builder.Uri;
		return true;
	}

	public Uri? ReadinessUri()
	{
		if (!TryGetBaseUri(out var baseUri) || baseUri is null)
		{
			return null;
		}

		var path = ReadinessPath.Trim();
		if (!HasValidReadinessPath())
		{
			return null;
		}

		var readinessUri = new Uri(baseUri, path.TrimStart('/'));
		return string.Equals(readinessUri.Scheme, baseUri.Scheme, StringComparison.OrdinalIgnoreCase)
			&& string.Equals(readinessUri.Host, baseUri.Host, StringComparison.OrdinalIgnoreCase)
			&& readinessUri.Port == baseUri.Port
			? readinessUri
			: null;
	}

	public bool HasValidReadinessPath()
	{
		var path = ReadinessPath.Trim();
		return path.StartsWith("/", StringComparison.Ordinal)
			&& !path.StartsWith("//", StringComparison.Ordinal)
			&& !path.Contains('#')
			&& !Uri.TryCreate(path, UriKind.Absolute, out _);
	}
}

public sealed class DatabaseOptions
{
	public const string SectionName = "Database";

	public bool ProbeEnabled { get; init; }
}

public sealed class ForwardedHeadersTrustOptions
{
	public const string SectionName = "ForwardedHeaders";

	public string[] TrustedProxyCidrs { get; init; } =
	[
		"127.0.0.1/32",
		"::1/128"
	];

	public bool TryGetTrustedProxyNetworks(
		out IReadOnlyList<IPNetwork> networks)
	{
		var parsedNetworks = new List<IPNetwork>();
		foreach (var value in TrustedProxyCidrs)
		{
			if (string.IsNullOrWhiteSpace(value)
				|| !IPNetwork.TryParse(value.Trim(), out var network))
			{
				networks = [];
				return false;
			}

			if (!parsedNetworks.Contains(network))
			{
				parsedNetworks.Add(network);
			}
		}

		networks = parsedNetworks;
		return parsedNetworks.Count > 0;
	}
}
