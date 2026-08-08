using DeployGuard.ControlPlane.Contracts;

namespace DeployGuard.ControlPlane;

public sealed class ExceptionHandlingMiddleware(
	RequestDelegate next,
	ILogger<ExceptionHandlingMiddleware> logger)
{
	public async Task InvokeAsync(HttpContext context)
	{
		try
		{
			await next(context);
		}
		catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested)
		{
			throw;
		}
		catch (Exception exception)
		{
			logger.LogError(
				exception,
				"Unhandled control-plane exception for request {RequestId}",
				context.TraceIdentifier);
			if (context.Response.HasStarted)
			{
				throw;
			}

			context.Response.Clear();
			context.Response.StatusCode = StatusCodes.Status500InternalServerError;
			await context.Response.WriteAsJsonAsync(
				new ErrorResponse("Internal server error", "internal_error"),
				cancellationToken: context.RequestAborted);
		}
	}
}
