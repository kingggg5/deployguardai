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
			logger.LogInformation(
				"HTTP request completed: {Method} {StatusCode} in {ElapsedMilliseconds} ms; request_id={RequestId}",
				context.Request.Method,
				context.Response.StatusCode,
				Stopwatch.GetElapsedTime(started).TotalMilliseconds,
				context.TraceIdentifier);
		}
	}
}
