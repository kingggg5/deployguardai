using System.Net;
using DeployGuard.ControlPlane.Configuration;
using Microsoft.Extensions.Options;
using Npgsql;

namespace DeployGuard.ControlPlane.Readiness;

public interface IUpstreamReadinessProbe
{
	Task<bool> IsReadyAsync(CancellationToken cancellationToken);
}

public interface IDatabaseReadinessProbe
{
	Task<ProbeResult> CheckAsync(CancellationToken cancellationToken);
}

public interface IControlPlaneReadiness
{
	Task<ReadinessSnapshot> CheckAsync(CancellationToken cancellationToken);
}

public sealed record ProbeResult(bool Ready, string Status);

public sealed record ReadinessSnapshot(
	bool Ready,
	string UpstreamStatus,
	string DatabaseStatus);

public sealed class UpstreamReadinessProbe(
	IHttpClientFactory httpClientFactory,
	IOptions<UpstreamOptions> options,
	TimeProvider timeProvider,
	ILogger<UpstreamReadinessProbe> logger) : IUpstreamReadinessProbe
{
	private readonly SemaphoreSlim _gate = new(1, 1);
	private DateTimeOffset _validUntil = DateTimeOffset.MinValue;
	private bool _lastResult;

	public async Task<bool> IsReadyAsync(CancellationToken cancellationToken)
	{
		var now = timeProvider.GetUtcNow();
		if (now < _validUntil)
		{
			return _lastResult;
		}

		await _gate.WaitAsync(cancellationToken);
		try
		{
			now = timeProvider.GetUtcNow();
			if (now < _validUntil)
			{
				return _lastResult;
			}

			_lastResult = await ProbeAsync(cancellationToken);
			_validUntil = now.Add(
				_lastResult ? TimeSpan.FromSeconds(2) : TimeSpan.FromMilliseconds(500));
			return _lastResult;
		}
		finally
		{
			_gate.Release();
		}
	}

	private async Task<bool> ProbeAsync(CancellationToken cancellationToken)
	{
		var readinessUri = options.Value.ReadinessUri();
		if (readinessUri is null)
		{
			return false;
		}

		try
		{
			using var request = new HttpRequestMessage(HttpMethod.Get, readinessUri);
			request.Headers.TryAddWithoutValidation(
				RequestIdMiddleware.HeaderName,
				Guid.NewGuid().ToString());
			using var response = await httpClientFactory
				.CreateClient("python-readiness")
				.SendAsync(
					request,
					HttpCompletionOption.ResponseHeadersRead,
					cancellationToken);
			return response.StatusCode is >= HttpStatusCode.OK
				and < HttpStatusCode.MultipleChoices;
		}
		catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
		{
			logger.LogWarning("Python upstream readiness probe timed out");
			return false;
		}
		catch (HttpRequestException exception)
		{
			logger.LogWarning(
				exception,
				"Python upstream readiness probe failed");
			return false;
		}
	}
}

public sealed class DatabaseReadinessProbe(
	IOptions<DatabaseOptions> options,
	IServiceProvider services,
	ILogger<DatabaseReadinessProbe> logger) : IDatabaseReadinessProbe
{
	public async Task<ProbeResult> CheckAsync(CancellationToken cancellationToken)
	{
		if (!options.Value.ProbeEnabled)
		{
			return new ProbeResult(true, "disabled");
		}

		var dataSource = services.GetService<NpgsqlDataSource>();
		if (dataSource is null)
		{
			return new ProbeResult(false, "unavailable");
		}

		try
		{
			await using var command = dataSource.CreateCommand("SELECT 1");
			var result = await command.ExecuteScalarAsync(cancellationToken);
			return Convert.ToInt32(result) == 1
				? new ProbeResult(true, "ready")
				: new ProbeResult(false, "unavailable");
		}
		catch (Exception exception) when (exception is not OperationCanceledException)
		{
			logger.LogWarning(exception, "PostgreSQL readiness probe failed");
			return new ProbeResult(false, "unavailable");
		}
	}
}

public sealed class ControlPlaneReadiness(
	IUpstreamReadinessProbe upstream,
	IDatabaseReadinessProbe database) : IControlPlaneReadiness
{
	public async Task<ReadinessSnapshot> CheckAsync(
		CancellationToken cancellationToken)
	{
		var upstreamTask = upstream.IsReadyAsync(cancellationToken);
		var databaseTask = database.CheckAsync(cancellationToken);
		await Task.WhenAll(upstreamTask, databaseTask);
		var upstreamReady = await upstreamTask;
		var databaseResult = await databaseTask;
		return new ReadinessSnapshot(
			upstreamReady && databaseResult.Ready,
			upstreamReady ? "ready" : "unavailable",
			databaseResult.Status);
	}
}
