using System.Diagnostics;

namespace DeployGuard.ControlPlane;

public sealed class RequestCompletionLoggingMiddleware(
	RequestDelegate next,
	ILogger<RequestCompletionLoggingMiddleware> logger)
{
	public async Task InvokeAsync(HttpContext context)
	{
		var started = Stopwatch.GetTimestamp();
		try
		{
			await next(context);
		}
		finally
		{
			var method = SanitizeForLog(context.Request.Method);
			logger.LogInformation(
				"HTTP request completed: {Method} {StatusCode} in {ElapsedMilliseconds} ms; request_id={RequestId}",
				method,
				context.Response.StatusCode,
				Stopwatch.GetElapsedTime(started).TotalMilliseconds,
				context.TraceIdentifier);
		}
	}

	private static string SanitizeForLog(string value)
	{
		const int maximumLength = 32;
		var sanitized = value
			.Replace("\r", string.Empty, StringComparison.Ordinal)
			.Replace("\n", string.Empty, StringComparison.Ordinal);
		return sanitized.Length <= maximumLength
			? sanitized
			: sanitized[..maximumLength];
	}
}
