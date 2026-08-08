FROM mcr.microsoft.com/dotnet/sdk:10.0-alpine AS build
WORKDIR /source

COPY src/DeployGuard.ControlPlane/DeployGuard.ControlPlane.csproj src/DeployGuard.ControlPlane/
RUN dotnet restore src/DeployGuard.ControlPlane/DeployGuard.ControlPlane.csproj

COPY src/DeployGuard.ControlPlane/ src/DeployGuard.ControlPlane/
RUN dotnet publish src/DeployGuard.ControlPlane/DeployGuard.ControlPlane.csproj \
    --configuration Release \
    --no-restore \
    --output /app/publish \
    /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0-alpine AS runtime
WORKDIR /app
COPY --from=build /app/publish .

ENV ASPNETCORE_HTTP_PORTS=8080 \
    DOTNET_EnableDiagnostics=0
EXPOSE 8080

USER $APP_UID
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -T 2 -O /dev/null http://127.0.0.1:8080/api/v1/health/live || exit 1

ENTRYPOINT ["dotnet", "DeployGuard.ControlPlane.dll"]
