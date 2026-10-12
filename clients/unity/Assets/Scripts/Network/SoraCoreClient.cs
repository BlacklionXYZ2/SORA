using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.WebSockets;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Threading;
using System.Threading.Tasks;
using Sora.Embodiment.Coordinates;

namespace Sora.Embodiment.Network
{
    public sealed class TargetPointDto
    {
        [JsonProperty("x")]
        public int X { get; set; }

        [JsonProperty("y")]
        public int Y { get; set; }

        public TargetPointDto() { }
        public TargetPointDto(int x, int y) { X = x; Y = y; }
    }

    public sealed class ScreenRectDto
    {
        [JsonProperty("x")]
        public int X { get; set; }

        [JsonProperty("y")]
        public int Y { get; set; }

        [JsonProperty("width")]
        public int Width { get; set; }

        [JsonProperty("height")]
        public int Height { get; set; }

        public ScreenRectDto() { }
        public ScreenRectDto(int x, int y, int width, int height)
        {
            X = x;
            Y = y;
            Width = width;
            Height = height;
        }

        public static ScreenRectDto FromScreenRect(ScreenRect r) =>
            new ScreenRectDto(r.X, r.Y, r.Width, r.Height);

        public ScreenRect ToScreenRect() => new ScreenRect(X, Y, Width, Height);
    }

    public sealed class MonitorDescriptorDto
    {
        [JsonProperty("id")]
        public string Id { get; set; } = string.Empty;

        [JsonProperty("primary")]
        public bool Primary { get; set; }

        [JsonProperty("rect")]
        public ScreenRectDto Rect { get; set; } = new ScreenRectDto();

        [JsonProperty("work_area")]
        public ScreenRectDto? WorkArea { get; set; }

        [JsonProperty("dpi_scale")]
        public float DpiScale { get; set; } = 1.0f;

        [JsonProperty("orientation")]
        public string Orientation { get; set; } = "landscape";

        public MonitorDescriptorDto() { }

        public static MonitorDescriptorDto FromDescriptor(MonitorDescriptor m) =>
            new MonitorDescriptorDto
            {
                Id = m.Id,
                Primary = m.Primary,
                Rect = ScreenRectDto.FromScreenRect(m.Rect),
                WorkArea = ScreenRectDto.FromScreenRect(m.WorkArea),
                DpiScale = m.DpiScale,
                Orientation = m.Orientation
            };

        public MonitorDescriptor ToDescriptor() =>
            new MonitorDescriptor(Id, Primary, Rect.ToScreenRect(), DpiScale, Orientation, WorkArea?.ToScreenRect());
    }

    public sealed class DisplayTopologyDto
    {
        [JsonProperty("virtual_desktop")]
        public ScreenRectDto VirtualDesktop { get; set; } = new ScreenRectDto();

        [JsonProperty("monitors")]
        public List<MonitorDescriptorDto> Monitors { get; set; } = new List<MonitorDescriptorDto>();

        [JsonProperty("revision")]
        public int Revision { get; set; } = 1;

        public DisplayTopologyDto() { }

        public static DisplayTopologyDto FromTopology(DisplayTopology t)
        {
            var dto = new DisplayTopologyDto
            {
                VirtualDesktop = ScreenRectDto.FromScreenRect(t.VirtualDesktop),
                Revision = t.Revision,
                Monitors = new List<MonitorDescriptorDto>()
            };
            foreach (var m in t.Monitors)
            {
                dto.Monitors.Add(MonitorDescriptorDto.FromDescriptor(m));
            }
            return dto;
        }
    }

    public sealed class EmbodimentCommandDto
    {
        [JsonProperty("command_id")]
        public string CommandId { get; set; } = string.Empty;

        [JsonProperty("verb")]
        public string Verb { get; set; } = string.Empty;

        [JsonProperty("target_point")]
        public TargetPointDto? TargetPoint { get; set; }

        [JsonProperty("target_rect")]
        public ScreenRectDto? TargetRect { get; set; }

        [JsonProperty("target_id")]
        public string? TargetId { get; set; }

        [JsonProperty("semantic_action_id")]
        public string? SemanticActionId { get; set; }

        [JsonProperty("semantic_action")]
        public string? SemanticAction { get; set; }

        [JsonProperty("semantic_phase")]
        public string? SemanticPhase { get; set; }

        [JsonProperty("presentation_style")]
        public string? PresentationStyle { get; set; }

        [JsonProperty("support_surfaces")]
        public List<SupportSurfaceDto> SupportSurfaces { get; set; } =
            new List<SupportSurfaceDto>();

        [JsonProperty("marker_duration_seconds")]
        public float MarkerDurationSeconds { get; set; } = 5f;

        [JsonProperty("state")]
        public string? State { get; set; }

        [JsonProperty("speed_px_per_sec")]
        public float SpeedPxPerSec { get; set; } = 150.0f;

        [JsonProperty("topology_revision")]
        public int TopologyRevision { get; set; } = 1;

        [JsonProperty("created_at")]
        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    }

    public sealed class SupportSurfaceDto
    {
        [JsonProperty("surface_id")]
        public string SurfaceId { get; set; } = string.Empty;

        [JsonProperty("kind")]
        public string Kind { get; set; } = "window_top";

        [JsonProperty("rect")]
        public ScreenRectDto Rect { get; set; } = new ScreenRectDto();

        [JsonProperty("state")]
        public string State { get; set; } = "active";

        [JsonProperty("observed_at")]
        public DateTime ObservedAt { get; set; }

        [JsonProperty("expires_at")]
        public DateTime ExpiresAt { get; set; }
    }

    public sealed class EmbodimentStateDto
    {
        [JsonProperty("visible")]
        public bool Visible { get; set; } = true;

        [JsonProperty("interpreted_target_id")]
        public string? InterpretedTargetId { get; set; }

        [JsonProperty("marker_position")]
        public TargetPointDto? MarkerPosition { get; set; }

        [JsonProperty("current_position")]
        public TargetPointDto CurrentPosition { get; set; } = new TargetPointDto();

        [JsonProperty("containing_monitor_id")]
        public string? ContainingMonitorId { get; set; }

        [JsonProperty("presentation_state")]
        public string PresentationState { get; set; } = "idle";

        [JsonProperty("topology_revision")]
        public int TopologyRevision { get; set; } = 1;

        [JsonProperty("connected_at")]
        public DateTime? ConnectedAt { get; set; }

        [JsonProperty("last_seen_at")]
        public DateTime? LastSeenAt { get; set; }
    }

    public sealed class EmbodimentProjectionDto
    {
        [JsonProperty("topology")]
        public DisplayTopologyDto Topology { get; set; } = new DisplayTopologyDto();

        [JsonProperty("revision")]
        public int Revision { get; set; } = 1;

        [JsonProperty("embodiment_state")]
        public EmbodimentStateDto? EmbodimentState { get; set; }

        [JsonProperty("connected")]
        public bool Connected { get; set; }
    }

    public sealed class EmbodimentFeedbackDto
    {
        [JsonProperty("event_id")]
        public string EventId { get; set; } = string.Empty;

        [JsonProperty("kind")]
        public string Kind { get; set; } = string.Empty;

        [JsonProperty("occurred_at")]
        public DateTime OccurredAt { get; set; }

        [JsonProperty("topology_revision")]
        public int TopologyRevision { get; set; }

        [JsonProperty("position")]
        public TargetPointDto Position { get; set; } = new TargetPointDto();

        [JsonProperty("subject_id")]
        public string? SubjectId { get; set; }

        [JsonProperty("correlation_id")]
        public string? CorrelationId { get; set; }

        [JsonProperty("detail")]
        public string? Detail { get; set; }

        [JsonProperty("magnitude")]
        public float? Magnitude { get; set; }
    }

    public sealed class DesktopActionResultDto
    {
        [JsonProperty("status")]
        public string Status { get; set; } = string.Empty;

        [JsonProperty("effect_attempted")]
        public bool EffectAttempted { get; set; }

        [JsonProperty("verified")]
        public bool Verified { get; set; }
    }

    // Audio-worker output only. Not an EmbodimentCommandDto or model-callable action.
    public sealed class VoiceSampleDto
    {
        [JsonProperty("op")] public string Op { get; set; } = "";
        [JsonProperty("stream_id")] public string StreamId { get; set; } = "";
        [JsonProperty("serial")] public long Serial { get; set; }
        [JsonProperty("emitted_at")] public DateTime EmittedAt { get; set; }
        [JsonProperty("playback_id")] public string? PlaybackId { get; set; }
        [JsonProperty("output_epoch")] public long? OutputEpoch { get; set; }
        [JsonProperty("emotion")] public string Emotion { get; set; } = "neutral";
        [JsonProperty("sequence")] public int Sequence { get; set; }
        [JsonProperty("position_ms")] public double PositionMs { get; set; }
        [JsonProperty("duration_ms")] public double DurationMs { get; set; }
        [JsonProperty("mouth_open")] public float MouthOpen { get; set; }
        // A, E, I, O, U shares of the mouth shape from the audio; null or all zero = Aa only.
        [JsonProperty("vowels")] public float[]? Vowels { get; set; }
        [JsonProperty("reason")] public string Reason { get; set; } = "disconnected";
    }

    public interface IDesktopPressTransport
    {
        Task<DesktopActionResultDto> PressDesktopTargetAsync(
            string targetId,
            string attemptId,
            string expectedNameAfter,
            string grantId,
            CancellationToken cancellationToken);
    }

    /// <summary>Live presentation transport. Commands are never replayed after reconnect.
    /// Callbacks run on transport threads; Unity consumers must marshal to Update().</summary>
    public sealed class SoraCoreClient : IAsyncDisposable, IDisposable, IDesktopPressTransport
    {
        private static readonly HashSet<string> PresentationStates = new HashSet<string>(StringComparer.Ordinal)
        {
            "idle", "thinking", "listening", "speaking", "waiting_for_agent", "reading", "typing",
            "sitting", "leaning", "climbing"
        };
        private static readonly HashSet<string> SemanticActions = new HashSet<string>(StringComparer.Ordinal)
        {
            "point", "press", "type", "touch", "place_object"
        };
        private static readonly HashSet<string> SemanticPhases = new HashSet<string>(StringComparer.Ordinal)
        {
            "navigate", "align", "reach", "contact", "verify", "retract", "completed", "cancelled", "failed"
        };
        private readonly Uri _baseUri;
        private readonly string _authToken, _deviceId, _connectGrant, _topologyGrant, _commandGrant;
        private readonly HttpClient _httpClient;
        private readonly Action<string>? _logger;
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
        private readonly HashSet<string> _seen = new HashSet<string>();
        private CancellationTokenSource? _cts;
        private Task? _loop;
        private ClientWebSocket? _socket;
        private bool _disposed;
        public bool IsConnected => _socket?.State == WebSocketState.Open;
        public int TopologyRevision { get; private set; }
        public event Action<EmbodimentCommandDto>? OnCommandReceived;
        public event Action<bool>? OnConnectionStateChanged;
        public event Action? OnResyncRequired;
        public event Action<EmbodimentProjectionDto>? OnProjectionReceived;
        public event Action<VoiceSampleDto>? OnVoiceSampleReceived;
        private string? _voiceStream;
        private long _voiceSerial;

        public SoraCoreClient(string host = "127.0.0.1", int port = 8000, string authToken = "",
            Action<string>? logger = null, string deviceId = "device-local",
            string connectGrant = "", string topologyGrant = "", string commandGrant = "")
        {
            // This initial transport is local-only. Do not send bearer credentials over remote HTTP.
            if (host != "127.0.0.1" && host != "localhost" && host != "::1")
                throw new ArgumentException("Embodiment transport requires a loopback host", nameof(host));
            _baseUri = new UriBuilder("http", host, port).Uri;
            _authToken = authToken; _logger = logger; _deviceId = deviceId;
            _connectGrant = connectGrant; _topologyGrant = topologyGrant; _commandGrant = commandGrant;
            _httpClient = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false });
            _httpClient.Timeout = TimeSpan.FromSeconds(10);
            if (!string.IsNullOrEmpty(authToken))
                _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", authToken);
            _httpClient.DefaultRequestHeaders.Add("X-SORA-Device-ID", deviceId);
        }

        public Task StartAsync(CancellationToken cancellationToken = default)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(SoraCoreClient));
            if (_loop != null) throw new InvalidOperationException("Client is already started");
            _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _loop = RunAsync(_cts.Token);
            return Task.CompletedTask;
        }

        private async Task RunAsync(CancellationToken ct)
        {
            int delay = 250;
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    _socket = new ClientWebSocket();
                    _socket.Options.SetRequestHeader("Authorization", "Bearer " + _authToken);
                    _socket.Options.SetRequestHeader("X-SORA-Device-ID", _deviceId);
                    _socket.Options.SetRequestHeader("X-SORA-Grant-ID", _connectGrant);
                    var uri = new UriBuilder(_baseUri) { Scheme = "ws", Path = "/api/v1/events/ws" }.Uri;
                    using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct))
                    {
                        timeout.CancelAfter(TimeSpan.FromSeconds(10));
                        await _socket.ConnectAsync(uri, timeout.Token).ConfigureAwait(false);
                    }
                    TopologyRevision = 0;
                    _seen.Clear();
                    _voiceStream = null; _voiceSerial = 0;
                    await SendAsync(new { client_kind = "embodiment", since_sequence = 0 }, ct).ConfigureAwait(false);
                    OnConnectionStateChanged?.Invoke(true);
                    var buffer = new byte[8192];
                    while (!ct.IsCancellationRequested && _socket.State == WebSocketState.Open)
                    {
                        using var message = new MemoryStream();
                        WebSocketReceiveResult frame;
                        do
                        {
                            frame = await _socket.ReceiveAsync(new ArraySegment<byte>(buffer), ct).ConfigureAwait(false);
                            if (frame.MessageType == WebSocketMessageType.Close) break;
                            if (frame.MessageType != WebSocketMessageType.Text || message.Length + frame.Count > 1024 * 1024)
                                throw new InvalidDataException("Invalid or oversized presentation message");
                            message.Write(buffer, 0, frame.Count);
                        } while (!frame.EndOfMessage);
                        if (frame.MessageType == WebSocketMessageType.Close) break;
                        ProcessIncomingMessage(Encoding.UTF8.GetString(message.ToArray()));
                    }
                }
                catch (Exception ex) when (!(ex is OperationCanceledException && ct.IsCancellationRequested))
                {
                    // Never log payloads, tokens or server-controlled exception text.
                    _logger?.Invoke("Presentation transport reconnecting: " + ex.GetType().Name);
                }
                finally
                {
                    _socket?.Dispose(); _socket = null;
                    TopologyRevision = 0;
                    OnConnectionStateChanged?.Invoke(false);
                }
                if (ct.IsCancellationRequested) break;
                try { await Task.Delay(delay, ct).ConfigureAwait(false); }
                catch (OperationCanceledException) { break; }
                delay = Math.Min(delay * 2, 10000);
            }
        }

        public void ProcessIncomingMessage(string jsonText)
        {
            var root = JObject.Parse(jsonText);
            string? type = (string?)root["type"];
            if (type == "embodiment.voice")
            {
                var sample = root["sample"]?.ToObject<VoiceSampleDto>();
                if (sample == null || !ValidIdentifier(sample.StreamId) || sample.Serial < 1 ||
                    (sample.Op != "begin" && sample.Op != "frame" && sample.Op != "reset")) return;
                if (_voiceStream == sample.StreamId && sample.Serial <= _voiceSerial) return;
                if (sample.Op != "reset" && (sample.PlaybackId == null ||
                    !ValidIdentifier(sample.PlaybackId) || sample.OutputEpoch == null ||
                    sample.OutputEpoch < 0 ||
                    (sample.Emotion != "neutral" && sample.Emotion != "warm" &&
                     sample.Emotion != "cheerful" && sample.Emotion != "concerned" &&
                     sample.Emotion != "focused"))) return;
                _voiceStream = sample.StreamId; _voiceSerial = sample.Serial;
                var sampleAge = DateTime.UtcNow - sample.EmittedAt.ToUniversalTime();
                if (sampleAge.TotalSeconds > 1 || sampleAge.TotalSeconds < -1 ||
                    (sample.Op == "frame" && (sample.Sequence < 0 || sample.Sequence > 1000000 ||
                    !Finite(sample.PositionMs) || sample.PositionMs < 0 || sample.PositionMs > 86400000 ||
                    !Finite(sample.DurationMs) || sample.DurationMs <= 0 || sample.DurationMs > 1000 ||
                    float.IsNaN(sample.MouthOpen) || float.IsInfinity(sample.MouthOpen) ||
                    sample.MouthOpen < 0 || sample.MouthOpen > 1)))
                {
                    sample.Op = "reset"; sample.PlaybackId = null; sample.Reason = "failed";
                }
                OnVoiceSampleReceived?.Invoke(sample);
                return;
            }
            if (type == "embodiment.snapshot")
            {
                var projection = root["projection"]?.ToObject<EmbodimentProjectionDto>()
                    ?? throw new InvalidDataException("Missing projection");
                TopologyRevision = projection.Revision;
                OnProjectionReceived?.Invoke(projection);
                return;
            }
            if (type == "resync_required")
            {
                TopologyRevision = 0;
                OnResyncRequired?.Invoke();
                return;
            }
            if (type != "embodiment.command") return;
            var command = root["command"]?.ToObject<EmbodimentCommandDto>();
            if (command == null || string.IsNullOrWhiteSpace(command.CommandId) ||
                TopologyRevision == 0 || command.TopologyRevision != TopologyRevision) return;
            var age = DateTime.UtcNow - command.CreatedAt.ToUniversalTime();
            if (age.TotalSeconds > 30 || age.TotalSeconds < -5 ||
                float.IsNaN(command.SpeedPxPerSec) || float.IsInfinity(command.SpeedPxPerSec) ||
                command.SpeedPxPerSec <= 0 || command.SpeedPxPerSec > 10000) return;
            if (command.Verb != "move_to" && command.Verb != "look_at" && command.Verb != "set_state" &&
                command.Verb != "show_marker" && command.Verb != "hide_marker" &&
                command.Verb != "presentation_phase" && command.Verb != "interaction_start" &&
                command.Verb != "set_supports") return;
            if ((command.Verb == "move_to" || command.Verb == "look_at" || command.Verb == "show_marker" ||
                 command.Verb == "interaction_start") &&
                command.TargetPoint == null) return;
            if (command.Verb == "set_state" &&
                (command.State == null || !PresentationStates.Contains(command.State))) return;
            if (command.Verb == "presentation_phase" &&
                (string.IsNullOrWhiteSpace(command.SemanticActionId) || command.SemanticPhase == null ||
                 !SemanticPhases.Contains(command.SemanticPhase))) return;
            if (command.SemanticAction != null &&
                ((command.Verb != "presentation_phase" && command.Verb != "interaction_start") ||
                 !SemanticActions.Contains(command.SemanticAction))) return;
            if (command.Verb == "interaction_start" &&
                (command.TargetRect == null || string.IsNullOrWhiteSpace(command.TargetId) ||
                 string.IsNullOrWhiteSpace(command.SemanticActionId) ||
                 (command.SemanticAction != "press" && command.SemanticAction != "type" &&
                  command.SemanticAction != "touch" && command.SemanticAction != "point"))) return;
            if (command.PresentationStyle != null &&
                ((command.Verb != "set_state" && command.Verb != "presentation_phase" &&
                  command.Verb != "interaction_start") ||
                 !ValidIdentifier(command.PresentationStyle))) return;
            if (float.IsNaN(command.MarkerDurationSeconds) || float.IsInfinity(command.MarkerDurationSeconds) ||
                command.MarkerDurationSeconds <= 0 || command.MarkerDurationSeconds > 30) return;
            if (!ValidSupports(command)) return;
            if (!_seen.Add(command.CommandId)) return;
            if (_seen.Count > 1024) throw new InvalidDataException("Presentation session command limit; reconnect required");
            OnCommandReceived?.Invoke(command);
        }

        private static bool Finite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);

        private static bool ValidIdentifier(string value)
        {
            if (value.Length < 1 || value.Length > 128 || !char.IsLetterOrDigit(value[0])) return false;
            foreach (var character in value)
                if (!char.IsLetterOrDigit(character) && character != '.' && character != '_' &&
                    character != ':' && character != '-') return false;
            return true;
        }

        private static bool ValidSupports(EmbodimentCommandDto command)
        {
            if (command.Verb != "set_supports")
                return command.SupportSurfaces == null || command.SupportSurfaces.Count == 0;
            if (command.SupportSurfaces == null || command.SupportSurfaces.Count > 32) return false;
            var ids = new HashSet<string>(StringComparer.Ordinal);
            foreach (var surface in command.SupportSurfaces)
            {
                if (surface == null || !ValidIdentifier(surface.SurfaceId) ||
                    !ids.Add(surface.SurfaceId) || surface.Kind != "window_top" ||
                    surface.Rect == null || surface.Rect.Width < 1 || surface.Rect.Height < 1 ||
                    (surface.State != "active" && surface.State != "moving" &&
                     surface.State != "minimized" && surface.State != "closed" &&
                     surface.State != "occluded") ||
                    surface.ExpiresAt.ToUniversalTime() <= DateTime.UtcNow ||
                    surface.ExpiresAt.ToUniversalTime() <= surface.ObservedAt.ToUniversalTime() ||
                    surface.ExpiresAt.ToUniversalTime() - surface.ObservedAt.ToUniversalTime() >
                        TimeSpan.FromSeconds(30)) return false;
            }
            return true;
        }

        private async Task SendAsync(object data, CancellationToken ct)
        {
            var bytes = Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(data));
            await _sendLock.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                if (_socket == null) throw new InvalidOperationException("No presentation connection");
                await _socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, ct).ConfigureAwait(false);
            }
            finally { _sendLock.Release(); }
        }

        public Task ReportStateAsync(EmbodimentStateDto state, CancellationToken ct = default) =>
            SendAsync(new { type = "embodiment.state", state }, ct);

        public Task ReportFeedbackAsync(EmbodimentFeedbackDto feedback,
            CancellationToken ct = default) =>
            SendAsync(new { type = "embodiment.feedback", @event = feedback }, ct);

        public async Task<EmbodimentProjectionDto?> GetEmbodimentProjectionAsync(CancellationToken ct = default)
        {
            using var response = await _httpClient.GetAsync(new Uri(_baseUri, "api/v1/projections/embodiment"), ct).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            return JsonConvert.DeserializeObject<EmbodimentProjectionDto>(await response.Content.ReadAsStringAsync().ConfigureAwait(false));
        }

        private async Task<bool> PostAsync(string path, object value, string grant, CancellationToken ct)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(_baseUri, path));
            request.Headers.Add("X-SORA-Grant-ID", grant);
            request.Content = new StringContent(JsonConvert.SerializeObject(value), Encoding.UTF8, "application/json");
            using var response = await _httpClient.SendAsync(request, ct).ConfigureAwait(false);
            return response.IsSuccessStatusCode;
        }

        public Task<bool> ReportTopologyAsync(DisplayTopology topology, CancellationToken ct = default) =>
            PostAsync("api/v1/embodiment/topology", DisplayTopologyDto.FromTopology(topology), _topologyGrant, ct);
        public Task<bool> SendCommandAsync(EmbodimentCommandDto command, CancellationToken ct = default) =>
            PostAsync("api/v1/embodiment/command", command, _commandGrant, ct);

        public async Task<DesktopActionResultDto> PressDesktopTargetAsync(
            string targetId, string attemptId, string expectedNameAfter, string grantId,
            CancellationToken cancellationToken)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post,
                new Uri(_baseUri, "api/v1/desktop/targets/" + Uri.EscapeDataString(targetId) + "/press"));
            request.Headers.Add("X-SORA-Grant-ID", grantId);
            request.Content = new StringContent(JsonConvert.SerializeObject(new {
                attempt_id = attemptId, expected_name_after = expectedNameAfter
            }), Encoding.UTF8, "application/json");
            using var response = await _httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            var result = JsonConvert.DeserializeObject<DesktopActionResultDto>(
                await response.Content.ReadAsStringAsync().ConfigureAwait(false));
            return result ?? throw new InvalidDataException("Missing desktop action result");
        }

        public async Task<DesktopActionResultDto> ContactPreparedInteractionAsync(
            string attemptId, CancellationToken cancellationToken)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post,
                new Uri(_baseUri, "api/v1/desktop/interactions/" +
                    Uri.EscapeDataString(attemptId) + "/contact"));
            request.Content = new StringContent("{}", Encoding.UTF8, "application/json");
            using var response = await _httpClient.SendAsync(request, cancellationToken)
                .ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            var result = JsonConvert.DeserializeObject<DesktopActionResultDto>(
                await response.Content.ReadAsStringAsync().ConfigureAwait(false));
            return result ?? throw new InvalidDataException("Missing desktop interaction result");
        }

        public async Task StopAsync()
        {
            _cts?.Cancel(); _socket?.Abort();
            if (_loop != null)
            {
                try { await _loop.ConfigureAwait(false); }
                catch (OperationCanceledException) { }
            }
            _loop = null; _cts?.Dispose(); _cts = null;
        }
        public async ValueTask DisposeAsync()
        {
            if (_disposed) return;
            _disposed = true;
            await StopAsync().ConfigureAwait(false);
            _httpClient.Dispose(); _sendLock.Dispose();
        }
        public void Dispose() => DisposeAsync().AsTask().GetAwaiter().GetResult();
    }
}
