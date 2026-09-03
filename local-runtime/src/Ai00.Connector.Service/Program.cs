using Ai00.Connector.Service;

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddWindowsService(options => options.ServiceName = "AI00 Local Runtime");
builder.Services.Configure<RuntimeOptions>(builder.Configuration.GetSection("LocalRuntime"));
builder.Services.AddHttpClient<DeviceGatewayClient>();
builder.Services.AddSingleton<SessionHostClient>();
builder.Services.AddHostedService<RuntimeWorker>();
await builder.Build().RunAsync();
