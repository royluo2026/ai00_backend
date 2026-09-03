using Ai00.Connector.Service;

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddWindowsService(options => options.ServiceName = "AI00 Connector");
builder.Services.Configure<RuntimeOptions>(builder.Configuration.GetSection("Connector"));
builder.Services.AddSingleton<IDeviceCredentialStore>(_ => new DeviceCredentialStore(
    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "Connector", "device.credential")));
builder.Services.AddHttpClient<DeviceGatewayClient>();
builder.Services.AddHttpClient<ConnectorGatewayClient>();
builder.Services.AddSingleton<IConnectorHeartbeatSink>(service =>
    service.GetRequiredService<ConnectorGatewayClient>());
builder.Services.AddSingleton<IConnectorHealthSource, FileConnectorHealthSource>();
builder.Services.AddSingleton<ConnectorHeartbeatReporter>();
builder.Services.AddSingleton<IConnectorPlanGateway>(service =>
    service.GetRequiredService<ConnectorGatewayClient>());
builder.Services.AddSingleton<SessionHostClient>();
builder.Services.AddSingleton<PlanSessionHostClient>();
builder.Services.AddSingleton<PlanJournal>(_ => new PlanJournal(
    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "AI00", "Connector", "plan-journal.json")));
builder.Services.AddSingleton<IPowerRequestNative, WindowsPowerRequestNative>();
builder.Services.AddSingleton<ISystemPowerGuard, SystemPowerGuard>();
builder.Services.AddSingleton<IConnectorPlanExecutor>(service =>
    new PowerGuardedPlanExecutor(
        service.GetRequiredService<PlanSessionHostClient>(),
        service.GetRequiredService<ISystemPowerGuard>()));
builder.Services.AddSingleton<PlanWorker>();
builder.Services.AddHostedService<RuntimeWorker>();
builder.Services.AddHostedService<ConnectorHeartbeatWorker>();
await builder.Build().RunAsync();
