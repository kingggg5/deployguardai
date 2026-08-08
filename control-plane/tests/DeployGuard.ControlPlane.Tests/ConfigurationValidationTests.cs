using DeployGuard.ControlPlane.Configuration;

namespace DeployGuard.ControlPlane.Tests;

public sealed class ConfigurationValidationTests
{
	[Theory]
	[InlineData("https://example.test/api/v1/health/ready")]
	[InlineData("//example.test/api/v1/health/ready")]
	[InlineData("api/v1/health/ready")]
	[InlineData("/api/v1/health/ready#fragment")]
	public void Readiness_path_rejects_cross_origin_or_ambiguous_values(string path)
	{
		var options = new UpstreamOptions
		{
			BaseUrl = "https://python-api.test",
			ReadinessPath = path
		};

		Assert.False(options.HasValidReadinessPath());
		Assert.Null(options.ReadinessUri());
	}

	[Fact]
	public void Readiness_path_stays_on_configured_origin()
	{
		var options = new UpstreamOptions
		{
			BaseUrl = "https://python-api.test:8443",
			ReadinessPath = "/api/v1/health/ready?source=control-plane"
		};

		var readinessUri = options.ReadinessUri();

		Assert.NotNull(readinessUri);
		Assert.Equal("python-api.test", readinessUri.Host);
		Assert.Equal(8443, readinessUri.Port);
	}

	[Fact]
	public void Trusted_proxy_cidrs_default_to_loopback_only()
	{
		var options = new ForwardedHeadersTrustOptions();

		Assert.True(options.TryGetTrustedProxyNetworks(out var networks));
		Assert.Equal(2, networks.Count);
		Assert.Contains(networks, network => network.Contains(System.Net.IPAddress.Loopback));
		Assert.Contains(networks, network => network.Contains(System.Net.IPAddress.IPv6Loopback));
		Assert.DoesNotContain(
			networks,
			network => network.Contains(System.Net.IPAddress.Parse("10.0.0.1")));
	}

	[Fact]
	public void Trusted_proxy_cidrs_reject_invalid_or_empty_configuration()
	{
		var invalid = new ForwardedHeadersTrustOptions
		{
			TrustedProxyCidrs = ["not-a-network"]
		};
		var empty = new ForwardedHeadersTrustOptions
		{
			TrustedProxyCidrs = []
		};

		Assert.False(invalid.TryGetTrustedProxyNetworks(out _));
		Assert.False(empty.TryGetTrustedProxyNetworks(out _));
	}
}
