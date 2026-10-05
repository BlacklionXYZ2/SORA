using Sora.Embodiment.Network;

if (args.Length == 1 && args[0] == "--displays")
{
    var native = Sora.Embodiment.Native.WindowsDisplayTopology.Read();
    Console.WriteLine(Newtonsoft.Json.JsonConvert.SerializeObject(new {
        source = "Win32 EnumDisplayMonitors/GetMonitorInfo/GetDpiForMonitor",
        recorded_at = DateTimeOffset.UtcNow, topology = DisplayTopologyDto.FromTopology(native)
    }, Newtonsoft.Json.Formatting.Indented));
    return;
}

// Synthetic, bounded Core integration probe; credentials supplied only by its test parent.
using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
await using var client = new SoraCoreClient(port: int.Parse(args[0]),
    authToken: Environment.GetEnvironmentVariable("SORA_PROBE_TOKEN") ?? "",
    connectGrant: "grant-connect", commandGrant: "grant-command", topologyGrant: "grant-topology");
var hydrated = new TaskCompletionSource<EmbodimentProjectionDto>(TaskCreationOptions.RunContinuationsAsynchronously);
var arrived = new TaskCompletionSource<EmbodimentCommandDto>(TaskCreationOptions.RunContinuationsAsynchronously);
client.OnProjectionReceived += p => hydrated.TrySetResult(p);
client.OnCommandReceived += c => arrived.TrySetResult(c);
await client.StartAsync(timeout.Token);
var projection = await hydrated.Task.WaitAsync(timeout.Token);
if (!projection.Connected || projection.Revision != 1) throw new Exception("Invalid initial snapshot");
var command = new EmbodimentCommandDto { CommandId = "probe-command", Verb = "move_to",
    TargetPoint = new TargetPointDto(50, 60), TopologyRevision = projection.Revision };
if (!await client.SendCommandAsync(command, timeout.Token)) throw new Exception("Command was rejected");
var received = await arrived.Task.WaitAsync(timeout.Token);
if (received.CommandId != command.CommandId) throw new Exception("Wrong command received");
foreach (string verb in new[] { "show_marker", "presentation_phase", "hide_marker" })
{
    var observed = new TaskCompletionSource<EmbodimentCommandDto>(TaskCreationOptions.RunContinuationsAsynchronously);
    void Handler(EmbodimentCommandDto c) { if (c.CommandId == "probe-" + verb) observed.TrySetResult(c); }
    client.OnCommandReceived += Handler;
    try
    {
        var presentation = new EmbodimentCommandDto { CommandId = "probe-" + verb, Verb = verb,
            TargetPoint = new TargetPointDto(50, 60), TargetId = "fixture-target",
            SemanticActionId = "fixture-action", SemanticPhase = "reach", TopologyRevision = projection.Revision };
        if (!await client.SendCommandAsync(presentation, timeout.Token)) throw new Exception("Presentation hook rejected");
        var delivered = await observed.Task.WaitAsync(timeout.Token);
        if (delivered.Verb != verb || delivered.TargetId != "fixture-target") throw new Exception("Presentation hook lost fields");
    }
    finally { client.OnCommandReceived -= Handler; }
}
await client.ReportStateAsync(new EmbodimentStateDto { CurrentPosition = new TargetPointDto(50, 60),
    ContainingMonitorId = "PRIMARY", TopologyRevision = projection.Revision,
    InterpretedTargetId = "fixture-target", MarkerPosition = new TargetPointDto(50, 60) }, timeout.Token);
// Await an observable server postcondition, not just successful socket writes.
for (int attempt = 0; attempt < 100; attempt++)
{
    var state = await client.GetEmbodimentProjectionAsync(timeout.Token);
    if (state?.EmbodimentState?.CurrentPosition.X == 50 && state.EmbodimentState.InterpretedTargetId == "fixture-target") break;
    if (attempt == 99) throw new Exception("Core did not accept reported state");
    await Task.Delay(20, timeout.Token);
}
await client.StopAsync();
int commandCount = 0;
client.OnCommandReceived += _ => commandCount++;
var reconnect = new TaskCompletionSource<EmbodimentProjectionDto>(TaskCreationOptions.RunContinuationsAsynchronously);
client.OnProjectionReceived += p => reconnect.TrySetResult(p);
await client.StartAsync(timeout.Token);
await reconnect.Task.WaitAsync(timeout.Token);
await Task.Delay(150, timeout.Token);
if (commandCount != 0) throw new Exception("Old command replayed after reconnect");
var changed = new TaskCompletionSource<EmbodimentProjectionDto>(TaskCreationOptions.RunContinuationsAsynchronously);
client.OnProjectionReceived += p => { if (p.Revision == 2) changed.TrySetResult(p); };
var topology = new Sora.Embodiment.Coordinates.DisplayTopology(
    new Sora.Embodiment.Coordinates.ScreenRect(0, 0, 800, 600),
    new[] { new Sora.Embodiment.Coordinates.MonitorDescriptor("PRIMARY", true,
        new Sora.Embodiment.Coordinates.ScreenRect(0, 0, 800, 600)) });
if (!await client.ReportTopologyAsync(topology, timeout.Token)) throw new Exception("Topology rejected");
await changed.Task.WaitAsync(timeout.Token);
if (await client.SendCommandAsync(command, timeout.Token)) throw new Exception("Stale topology accepted");
await client.StopAsync();
Console.WriteLine("PASS: snapshot, authorized command, marker/semantic hooks, interpreted target state, reconnect without replay, topology invalidation, bounded stop");
