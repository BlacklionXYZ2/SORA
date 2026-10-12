using System.Text.Json;

namespace Sora.DesktopShell;

public sealed record VoiceDevice(string Key, int Inputs, int Outputs, int? Index);
public sealed record VoiceProjection(string State, string Message, bool Running, bool Enabled,
    bool? MicrophoneOpen, IReadOnlyList<VoiceDevice> Devices)
{
    public static VoiceProjection Parse(JsonElement data, bool? enabled = null)
    {
        if (data.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Voice status is unavailable.");
        var state = TaskPresentation.Text(data, "state"); var message = TaskPresentation.Text(data, "message");
        if (state is not ("stopped" or "loading" or "ready" or "listening" or "recording" or "transcribing" or "thinking" or "speaking" or "error")
            || message.Length > 1000 || !data.TryGetProperty("running", out var running) || running.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("Unknown/incomplete local voice status.");
        var allowed = data.TryGetProperty("enabled", out var flag) && flag.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? flag.GetBoolean() : enabled ?? throw new InvalidDataException("Voice policy status is unavailable.");
        bool? microphone = data.TryGetProperty("microphone_open", out var mic) && mic.ValueKind is JsonValueKind.True or JsonValueKind.False ? mic.GetBoolean() : null;
        // Older Core status lacks explicit capture metadata: never infer Closed from general state.
        if (!data.TryGetProperty("devices", out var rows) || rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 128)
            throw new InvalidDataException("Voice device inventory exceeds its bound.");
        var devices = new List<VoiceDevice>();
        foreach (var row in rows.EnumerateArray()) {
            var key = TaskPresentation.Text(row, "key");
            if (key.Length is < 1 or > 512 || key.Any(char.IsControl)
                || !row.TryGetProperty("input_channels", out var input) || !input.TryGetInt32(out var inputs) || inputs is < 0 or > 256
                || !row.TryGetProperty("output_channels", out var output) || !output.TryGetInt32(out var outputs) || outputs is < 0 or > 256)
                throw new InvalidDataException("Voice device metadata is invalid.");
            int? index = null;
            if (row.TryGetProperty("index", out var position)) {
                if (!position.TryGetInt32(out var value) || value is < 0 or > 4096) throw new InvalidDataException("Voice device index is invalid.");
                index = value;
            }
            devices.Add(new(key, inputs, outputs, index));
        }
        return new(state, message, running.GetBoolean(), allowed, microphone, devices);
    }
    public bool Can(string action) => action switch {
        "start" => Enabled && State is "stopped" or "error",
        "begin" => Enabled && Running && State is "ready" or "recording" or "transcribing" or "thinking" or "speaking",
        "end" or "stop" or "stop_output" => Enabled && Running,
        "close" => true,
        _ => false
    };
    public string MicrophoneLabel(bool current) => !current ? MicrophoneOpen == true
        ? "Mic UNKNOWN · last reported recording" : "Mic status UNKNOWN"
        : MicrophoneOpen == true ? (State == "listening" ? "Mic ON · listening for her name" : "Mic ON · recording")
        : MicrophoneOpen == false ? "Mic closed · worker report" : "Mic status UNKNOWN";
}

// Release/loss intent is retained while Begin awaits its acknowledgement, never replaying Begin.
public sealed class PressToTalk(Func<string, Task> action)
{
    private bool beginning;
    private string releaseAction = "end";
    public bool Held { get; private set; }
    public bool Beginning => beginning;
    public async Task BeginAsync()
    {
        if (Held || beginning) return;
        Held = true; releaseAction = "end"; beginning = true;
        try {
            await action("begin");
            if (!Held) await action(releaseAction);
        }
        catch {
            // A release/loss is explicit safety intent, not retry of an uncertain Begin.
            if (!Held) { try { await action("stop"); } catch { } }
            Held = false; throw;
        }
        finally { beginning = false; }
    }
    public async Task ReleaseAsync(bool discard = false)
    {
        if (!Held && !beginning) return;
        if (discard) releaseAction = "stop";
        Held = false;
        if (!beginning) await action(releaseAction);
    }
}
