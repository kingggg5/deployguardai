namespace DeployGuard.ControlPlane;

public sealed class RequestIdMiddleware(RequestDelegate next)
{
	public const string HeaderName = "X-Request-ID";
	public const string ContextItemName = "deployguard.request_id";

	public async Task InvokeAsync(HttpContext context)
	{
		var requestId = Resolve(context.Request.Headers[HeaderName].ToString());
		context.TraceIdentifier = requestId;
		context.Items[ContextItemName] = requestId;
		context.Request.Headers[HeaderName] = requestId;
		context.Response.OnStarting(() =>
		{
			context.Response.Headers[HeaderName] = requestId;
			context.Response.Headers["X-DeployGuard-Control-Plane"] = "dotnet-10";
			context.Response.Headers["X-Content-Type-Options"] = "nosniff";
			context.Response.Headers.Remove("Server");
			return Task.CompletedTask;
		});
		await next(context);
	}

	private static string Resolve(string candidate)
	{
		var value = candidate.Trim();
		if (value.Length is > 0 and <= 80
			&& value.All(character =>
				char.IsAsciiLetterOrDigit(character)
				|| character is '.' or ':' or '_' or '-'))
		{
			return value;
		}

		return Guid.NewGuid().ToString();
	}
}
