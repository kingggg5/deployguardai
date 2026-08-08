using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace DeployGuard.ControlPlane.Tests;

public sealed class RequestCompletionLoggingMiddlewareTests
{
	[Fact]
	public async Task InvokeAsync_RemovesLineBreaksFromRequestMethod()
	{
		var logger = new CapturingLogger<RequestCompletionLoggingMiddleware>();
		var middleware = new RequestCompletionLoggingMiddleware(
			_ => Task.CompletedTask,
			logger);
		var context = new DefaultHttpContext
		{
			TraceIdentifier = "request-safe",
		};
		context.Request.Method = "GET\r\nforged";

		await middleware.InvokeAsync(context);

		var message = Assert.Single(logger.Messages);
		Assert.DoesNotContain('\r', message);
		Assert.DoesNotContain('\n', message);
		Assert.Contains("GETforged", message, StringComparison.Ordinal);
	}

	private sealed class CapturingLogger<T> : ILogger<T>
	{
		public List<string> Messages { get; } = [];

		public IDisposable? BeginScope<TState>(TState state)
			where TState : notnull => null;

		public bool IsEnabled(LogLevel logLevel) => true;

		public void Log<TState>(
			LogLevel logLevel,
			EventId eventId,
			TState state,
			Exception? exception,
			Func<TState, Exception?, string> formatter)
		{
			Messages.Add(formatter(state, exception));
		}
	}
}
