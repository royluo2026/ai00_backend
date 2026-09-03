using Ai00.Connector.Service;

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddWindowsService(options => options.ServiceName = "AI00 Connector");
builder.Services.Configure<RuntimeOptions>(builder.Configuration.GetSection("Connector"));
builder.Services.AddSingleton<IDeviceCredentialStore>(_ => new DeviceCredentialStore(
    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "Connector", "device.credential")));
builder.Services.AddHttpClient<DeviceGatewayClient>();
builder.Services.AddSingleton<SessionHostClient>();
builder.Services.AddHostedService<RuntimeWorker>();
await builder.Build().RunAsync();
