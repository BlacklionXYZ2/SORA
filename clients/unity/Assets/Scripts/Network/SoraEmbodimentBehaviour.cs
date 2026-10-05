using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Sora.Embodiment.Avatar;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Debugging;
using Sora.Embodiment.Interaction;
using Sora.Embodiment.Native;
using Sora.Embodiment.Presentation;
using Sora.Embodiment.Voice;
using UnityEngine;

namespace Sora.Embodiment.Network
{
    /// <summary>Scene wiring for the transport. Requires a configured scene; not a VRM loader.</summary>
    public sealed class SoraEmbodimentBehaviour : MonoBehaviour
    {
        [SerializeField] private AvatarLocomotion locomotion = null!;
        [SerializeField] private AvatarLookAt gaze = null!;
        [SerializeField] private DebugOverlayHUD hud = null!;
        [SerializeField] private AvatarPresentationController presentation = null!;
        [SerializeField] private AvatarReachController reach = null!;
        [SerializeField] private AvatarVoicePresentationController voicePresentation = null!;
        [SerializeField] private int port = 8000;
        private readonly ConcurrentQueue<Action> _pending = new ConcurrentQueue<Action>();
        private readonly ConcurrentQueue<VoiceSampleDto> _voicePending = new ConcurrentQueue<VoiceSampleDto>();
        private string? _voiceStream;
        private SoraCoreClient? _client;
        private DisplayTopology? _topology;
        private float _nextReport;
        private bool _reportPending;
        private bool _feedbackPending;
        private readonly EmbodimentFeedbackBuffer _feedback =
            new EmbodimentFeedbackBuffer(() => Time.realtimeSinceStartupAsDouble);
        private AttentionMarker _marker = null!;
        private DisplayTopology? _nativeTopology;
        private bool _topologyPending;
        private float _nextTopologyReport;
        private AvatarInteractionEnvironment? _interactionEnvironment;
        private AvatarSupportSurfaceController? _supportSurfaces;
        private EmbodimentInteractionController? _interactionController;
        private readonly List<object> _interactionEvidence = new List<object>();
        private string? _interactionEvidencePath;
        private string _lastInteractionInstance = string.Empty;
        private string _lastInteractionAction = string.Empty;
        private string? _lastInteractionTarget;
        public event Action<DisplayTopology>? OnTopologyAccepted;
        public bool HasAcceptedTopology => _topology != null;
        public bool AvatarReady { get; set; }
        public bool CanAcceptPhysicalGrab => AvatarReady &&
            (_interactionController == null || !_interactionController.IsActive);
        public void SuspendPresentation()
        {
            _topology = null;
            _nativeTopology = null;
            StopPresentation(VoicePresentationResetReason.Paused);
        }

        private void StopPresentation(VoicePresentationResetReason reason)
        {
            var point = locomotion.GetCurrentGlobalPixelPosition();
            locomotion.TeleportTo(point.GlobalX, point.GlobalY);
            gaze.ResetGaze();
            _marker.Hide();
            presentation.ResetToIdle();
            voicePresentation.ResetAll(reason);
        }

        public void Configure(AvatarLocomotion motion, AvatarLookAt look, DebugOverlayHUD debug,
            AttentionMarker marker, AvatarPresentationController presentationController,
            AvatarReachController reachController,
            AvatarVoicePresentationController voicePresentationController)
        {
            locomotion = motion;
            gaze = look;
            hud = debug;
            _marker = marker;
            presentation = presentationController;
            reach = reachController;
            voicePresentation = voicePresentationController;
        }

        public void ConfigureSupportPhysics(AvatarSupportSurfaceController supportSurfaces)
        {
            _supportSurfaces = supportSurfaces ??
                throw new ArgumentNullException(nameof(supportSurfaces));
        }

        public void ConfigurePhysicalFeedback(AvatarGrabController grab,
            AvatarSimplePhysicsController physics, AvatarSupportSurfaceController supports)
        {
            if (grab == null || physics == null || supports == null)
                throw new ArgumentNullException(nameof(grab));
            grab.Grabbed += () => QueueFeedback("grabbed");
            grab.Released += velocity => QueueFeedback("released", magnitude: velocity.magnitude);
            grab.Clicked += () => QueueFeedback("clicked");
            grab.Poked += () => QueueFeedback("poked");
            physics.Fell += velocity => QueueFeedback("fell", magnitude: velocity.magnitude);
            physics.LandedOnSupport += (velocity, support) => QueueFeedback(
                "landed", support.SurfaceId, magnitude: velocity.magnitude);
            supports.SupportRemoved += (surfaceId, reason) => QueueFeedback(
                "support_removed", surfaceId, detail: reason);
        }

        public void SetNativeTopology(DisplayTopology topology)
        {
            if (_nativeTopology != null && WindowsDisplayTopology.SameLayout(_nativeTopology, topology)) return;
            _nativeTopology = topology;
            _topology = null;
            locomotion.SetTopology(topology);
            gaze.SetTopology(topology);
            gaze.ResetGaze();
            _marker.Hide();
            voicePresentation.ResetAll(VoicePresentationResetReason.Paused);
            _nextTopologyReport = 0;
        }
        private readonly Dictionary<string, Action<EmbodimentCommandDto>> _commands =
            new Dictionary<string, Action<EmbodimentCommandDto>>();

        private async void Start()
        {
            var configuredPort = Environment.GetEnvironmentVariable("SORA_CORE_PORT");
            if (!string.IsNullOrEmpty(configuredPort))
            {
                if (!int.TryParse(configuredPort, out port) || port < 1 || port > 65535)
                { Debug.LogError("Invalid SORA_CORE_PORT"); enabled = false; return; }
            }
            // Bounded P09 registrations; later physical actions use the P11 lifecycle registry.
            _commands["move_to"] = c => locomotion.MoveTo(c.TargetPoint!.X, c.TargetPoint.Y, c.SpeedPxPerSec);
            _commands["look_at"] = c => gaze.LookAtScreenPoint(c.TargetPoint!.X, c.TargetPoint.Y,
                presentation.CurrentState == "idle" ? 1 : presentation.CurrentProfile.GazeWeight);
            _commands["show_marker"] = c => _marker.Show(c, _topology!);
            _commands["hide_marker"] = c => _marker.Hide();
            _commands["presentation_phase"] = c =>
            {
                _marker.ConsumePhase(c);
                if (!string.IsNullOrWhiteSpace(c.SemanticAction))
                    presentation.PresentAction(c.SemanticAction!, c.PresentationStyle);
            };
            _commands["interaction_start"] = StartInteraction;
            _commands["set_supports"] = ApplySupportSnapshot;
            _commands["set_state"] = c =>
            {
                presentation.SetState(c.State!, c.PresentationStyle);
                if (c.State == "idle")
                {
                    var current = locomotion.GetCurrentGlobalPixelPosition();
                    locomotion.TeleportTo(current.GlobalX, current.GlobalY);
                    gaze.ResetGaze();
                    _marker.Hide();
                }
            };
            // No bearer credentials serialized into scenes/prefabs.
            _client = new SoraCoreClient(port: port,
                deviceId: Environment.GetEnvironmentVariable("SORA_EMBODIMENT_DEVICE_ID") ?? "device-local",
                authToken: Environment.GetEnvironmentVariable("SORA_API_TOKEN") ?? "",
                connectGrant: Environment.GetEnvironmentVariable("SORA_EMBODIMENT_CONNECT_GRANT") ?? "",
                topologyGrant: Environment.GetEnvironmentVariable("SORA_EMBODIMENT_TOPOLOGY_GRANT") ?? "");
            _interactionEvidencePath = Environment.GetEnvironmentVariable(
                "SORA_INTERACTION_EVIDENCE_PATH");
            _interactionEnvironment = new AvatarInteractionEnvironment(
                gaze, reach, presentation, locomotion);
            var registry = new EmbodimentActionRegistry();
            registry.RegisterPointPresentation();
            registry.Register(new AuthorizedPressAction((context, cancellationToken) =>
                _client.ContactPreparedInteractionAsync(context.InstanceId, cancellationToken)));
            registry.Register(new AuthorizedTypeAction((context, cancellationToken) =>
                _client.ContactPreparedInteractionAsync(context.InstanceId, cancellationToken)));
            registry.Register(new DelegateEmbodimentAction(
                "touch",
                new[] { "locomotion", "gaze", "reach" },
                _ => InteractionStepResult.Succeeded,
                _ => InteractionStepResult.Succeeded,
                effectMayChangeExternalState: false));
            _interactionController = new EmbodimentInteractionController(
                registry,
                _interactionEnvironment,
                new PresentationOwnershipArbiter(),
                () => Time.realtimeSinceStartupAsDouble);
            _interactionController.OnPhaseChanged += RecordInteractionPhase;
            _client.OnProjectionReceived += p => _pending.Enqueue(() => Hydrate(p));
            _client.OnCommandReceived += c => _pending.Enqueue(() => Apply(c));
            _client.OnVoiceSampleReceived += sample =>
            {
                if (_voicePending.Count >= 32)
                {
                    while (_voicePending.TryDequeue(out _)) { }
                    _voicePending.Enqueue(new VoiceSampleDto {
                        Op = "reset", StreamId = sample.StreamId, Reason = "failed" });
                }
                else _voicePending.Enqueue(sample);
            };
            _client.OnConnectionStateChanged += connected => _pending.Enqueue(() =>
            {
                if (hud != null) hud.SetConnectionState(connected);
                _interactionEnvironment?.SetConnected(connected && _topology != null);
                if (!connected)
                {
                    _topology = null;
                    if (locomotion != null)
                    {
                        var point = locomotion.GetCurrentGlobalPixelPosition();
                        locomotion.TeleportTo(point.GlobalX, point.GlobalY);
                    }
                    if (gaze != null) gaze.ResetGaze();
                    _marker.Hide();
                    presentation.ResetToIdle();
                    voicePresentation.ResetAll(VoicePresentationResetReason.Disconnected);
                    while (_voicePending.TryDequeue(out _)) { }
                    _voiceStream = null;
                    _nextTopologyReport = 0;
                }
            });
            await _client.StartAsync();
        }

        private void Hydrate(EmbodimentProjectionDto projection)
        {
            var dto = projection.Topology;
            var accepted = new DisplayTopology(dto.VirtualDesktop.ToScreenRect(),
                dto.Monitors.Select(m => m.ToDescriptor()), projection.Revision);
            if (_nativeTopology == null || !WindowsDisplayTopology.SameLayout(_nativeTopology, accepted))
            { _topology = null; StopPresentation(VoicePresentationResetReason.Paused); return; }
            _topology = accepted;
            locomotion.SetTopology(_topology);
            gaze.SetTopology(_topology);
            if (hud != null) hud.SetTopology(_topology);
            _marker.Hide();
            OnTopologyAccepted?.Invoke(_topology);
            _interactionEnvironment?.SetConnected(_client?.IsConnected == true);
            var state = projection.EmbodimentState;
            if (state != null && state.TopologyRevision == _topology.Revision &&
                _topology.IsPointOnDisplay(state.CurrentPosition.X, state.CurrentPosition.Y))
            {
                var safe = OverlayPlacement.SafeAnchor(_topology, state.CurrentPosition.X, state.CurrentPosition.Y);
                locomotion.TeleportTo(safe.X, safe.Y);
                if (state.PresentationState != "moving" && state.PresentationState != "looking")
                    presentation.SetState(state.PresentationState);
            }
        }

        private void ApplyVoice(VoiceSampleDto sample)
        {
            if (_voiceStream != sample.StreamId)
            { voicePresentation.ResetTransport(); _voiceStream = sample.StreamId; }
            if (sample.Op == "reset")
            {
                string reasonName = sample.Reason.Replace("_", "");
                if (!Enum.TryParse(reasonName, true, out VoicePresentationResetReason reason))
                    reason = VoicePresentationResetReason.Failed;
                if (sample.PlaybackId == null || sample.OutputEpoch == null)
                    voicePresentation.ResetAll(reason);
                else voicePresentation.Reset(sample.PlaybackId, sample.OutputEpoch.Value, reason);
                return;
            }
            if (!AvatarReady || _topology == null || sample.PlaybackId == null ||
                sample.OutputEpoch == null) return;
            if ((DateTime.UtcNow - sample.EmittedAt.ToUniversalTime()).TotalSeconds > 1)
            { voicePresentation.ResetAll(VoicePresentationResetReason.Failed); return; }
            if (sample.Op == "begin")
                voicePresentation.Begin(sample.PlaybackId, sample.OutputEpoch.Value, sample.Emotion);
            else if (!voicePresentation.ApplyFrame(new VoicePresentationFrame(sample.PlaybackId,
                sample.OutputEpoch.Value, sample.Sequence, sample.PositionMs, sample.DurationMs,
                sample.MouthOpen, sample.Emotion)))
                voicePresentation.ResetAll(VoicePresentationResetReason.Failed);
        }
        private void Apply(EmbodimentCommandDto command)
        {
            if (_topology == null || command.TopologyRevision != _topology.Revision) return;
            if ((DateTime.UtcNow - command.CreatedAt.ToUniversalTime()).TotalSeconds > 30) return;
            if ((presentation.IsPoseOwned || _interactionController?.IsActive == true) &&
                (command.Verb == "move_to" || command.Verb == "look_at" ||
                 command.Verb == "set_state")) return;
            var point = command.TargetPoint;
            if (point != null && !_topology.IsPointOnDisplay(point.X, point.Y)) return;
            if (_commands.TryGetValue(command.Verb, out var handler)) handler(command);
        }

        private void StartInteraction(EmbodimentCommandDto command)
        {
            if (!AvatarReady || _topology == null || _interactionController == null ||
                _interactionController.IsActive || command.TargetPoint == null ||
                command.TargetRect == null || string.IsNullOrWhiteSpace(command.TargetId) ||
                string.IsNullOrWhiteSpace(command.SemanticActionId) ||
                string.IsNullOrWhiteSpace(command.SemanticAction)) return;
            var point = command.TargetPoint;
            var transformer = new CoordinateTransformer();
            var world = transformer.GlobalToWorld(point.X, point.Y, _topology);
            var current = locomotion.GetCurrentGlobalPixelPosition();
            var side = point.X >= current.GlobalX ? -1 : 1;
            var standing = OverlayPlacement.SafeAnchor(
                _topology, point.X + side * 60, point.Y + 180);
            var revision = command.TopologyRevision;
            var target = new InteractionTarget(
                command.TargetId!,
                new Vector3(world.X, world.Y, world.Z),
                () => _topology != null && _topology.Revision == revision &&
                    _topology.IsPointOnDisplay(point.X, point.Y),
                point.X,
                point.Y,
                standing.X,
                standing.Y);
            _interactionEvidence.Clear();
            _lastInteractionInstance = command.SemanticActionId!;
            _lastInteractionAction = command.SemanticAction!;
            _lastInteractionTarget = command.TargetId;
            RecordInteractionEvent(command.SemanticActionId!, command.SemanticAction!,
                "target_selected", command.TargetId!);
            if (!_interactionController.Start(command.SemanticActionId!,
                command.SemanticAction!, target, 20))
                RecordInteractionTerminal();
        }

        private void ApplySupportSnapshot(EmbodimentCommandDto command)
        {
            if (_supportSurfaces == null || _topology == null) return;
            var surfaces = new List<AvatarSupportSurface>();
            foreach (var dto in command.SupportSurfaces)
            {
                if (!Enum.TryParse<AvatarSupportSurfaceState>(dto.State, true, out var state))
                    return;
                surfaces.Add(new AvatarSupportSurface(dto.SurfaceId, dto.Rect.ToScreenRect(),
                    state, dto.ExpiresAt.ToUniversalTime()));
            }
            _supportSurfaces.ApplySnapshot(surfaces, command.TopologyRevision, DateTime.UtcNow);
        }

        private void Update()
        {
            // Bound main-thread processing; all Unity calls occur here.
            for (int i = 0; i < 100 && _pending.TryDequeue(out var action); i++) action();
            for (int i = 0; i < 32 && _voicePending.TryDequeue(out var sample); i++) ApplyVoice(sample);
            if (_interactionController != null)
            {
                var wasActive = _interactionController.IsActive;
                _interactionController.Tick();
                if (wasActive && !_interactionController.IsActive) RecordInteractionTerminal();
            }
            if (_pending.Count > 1024) { enabled = false; _client?.Dispose(); return; }
            if (_nativeTopology != null && _topology == null && _client?.IsConnected == true &&
                !_topologyPending && Time.unscaledTime >= _nextTopologyReport) ReportTopology();
            if (_topology != null && _client?.IsConnected == true && !_reportPending && Time.unscaledTime >= _nextReport)
            {
                _nextReport = Time.unscaledTime + 0.5f;
                ReportPosition();
            }
            if (_topology != null && _client?.IsConnected == true && !_feedbackPending &&
                _feedback.Count > 0) ReportFeedback();
        }

        private void RecordInteractionPhase(InteractionContext context, InteractionPhase phase)
        {
            var name = phase == InteractionPhase.SemanticEffect ? "invoke" :
                phase.ToString().ToLowerInvariant();
            RecordInteractionEvent(context.InstanceId, context.ActionId, name,
                context.Target.TargetId);
        }

        private void RecordInteractionTerminal()
        {
            if (_interactionController == null) return;
            RecordInteractionEvent(
                _lastInteractionInstance,
                _lastInteractionAction,
                _interactionController.Status.ToString().ToLowerInvariant(),
                _lastInteractionTarget,
                _interactionController.Reason,
                _interactionController.EffectAttempted,
                _interactionController.Verified);
            string status = _interactionController.Status.ToString().ToLowerInvariant();
            if (status == "completed")
                QueueFeedback("completed", _lastInteractionTarget,
                    _lastInteractionInstance, _interactionController.Reason);
            else if (status == "failed" || status == "unknownoutcome" || status == "cancelled")
                QueueFeedback("failed", _lastInteractionTarget,
                    _lastInteractionInstance, _interactionController.Reason ?? status);
        }

        private void QueueFeedback(string kind, string? subjectId = null,
            string? correlationId = null, string? detail = null, float? magnitude = null)
        {
            if (_topology == null || !AvatarReady) return;
            var position = locomotion.GetCurrentGlobalPixelPosition();
            _feedback.TryEnqueue(kind, new TargetPointDto(position.GlobalX, position.GlobalY),
                _topology.Revision, subjectId, correlationId, detail, magnitude);
        }

        private void RecordInteractionEvent(string instanceId, string actionId, string phase,
            string? targetId, string? reason = null, bool effectAttempted = false,
            bool verified = false)
        {
            if (string.IsNullOrWhiteSpace(_interactionEvidencePath)) return;
            var position = locomotion.GetCurrentGlobalPixelPosition();
            _interactionEvidence.Add(new {
                recorded_at = DateTime.UtcNow,
                instance_id = instanceId,
                action_id = actionId,
                phase,
                target_id = targetId,
                position = new { x = position.GlobalX, y = position.GlobalY },
                reason,
                effect_attempted = effectAttempted,
                verified
            });
            var fullPath = Path.GetFullPath(_interactionEvidencePath!);
            var directory = Path.GetDirectoryName(fullPath);
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            File.WriteAllText(fullPath, JsonConvert.SerializeObject(new {
                schema_version = "1.0",
                events = _interactionEvidence
            }, Formatting.Indented));
        }

        private async void ReportTopology()
        {
            if (_nativeTopology == null || _client == null) return;
            _topologyPending = true;
            _nextTopologyReport = Time.unscaledTime + 5f;
            try { await _client.ReportTopologyAsync(_nativeTopology); }
            catch (Exception) { /* Retry is bounded and only a matching Core snapshot enables commands. */ }
            finally { _topologyPending = false; }
        }

        private async void ReportPosition()
        {
            if (_client == null || _topology == null) return;
            var point = locomotion.GetCurrentGlobalPixelPosition();
            var monitor = _topology.FindMonitor(point.GlobalX, point.GlobalY);
            if (monitor == null) return;
            _reportPending = true;
            try
            {
                await _client.ReportStateAsync(new EmbodimentStateDto {
                    Visible = AvatarReady,
                    CurrentPosition = new TargetPointDto(point.GlobalX, point.GlobalY),
                    ContainingMonitorId = monitor.Id, TopologyRevision = _topology.Revision,
                    InterpretedTargetId = _marker.TargetId, MarkerPosition = _marker.Point,
                    PresentationState = locomotion.IsMoving ? "moving" :
                        gaze.IsLooking ? "looking" : presentation.CurrentState });
            }
            catch (Exception) { /* Transport reconnect owns recovery; never log private payloads. */ }
            finally { _reportPending = false; }
        }

        private async void ReportFeedback()
        {
            if (_client == null || !_feedback.TryDequeue(out var feedback) || feedback == null)
                return;
            _feedbackPending = true;
            try
            {
                if ((DateTime.UtcNow - feedback.OccurredAt).TotalSeconds <= 30)
                    await _client.ReportFeedbackAsync(feedback);
            }
            catch (Exception) { /* Feedback is edge-only and never replayed after transport failure. */ }
            finally { _feedbackPending = false; }
        }

        private async void OnDestroy()
        {
            if (voicePresentation != null)
                voicePresentation.ResetAll(VoicePresentationResetReason.Disconnected);
            if (_client != null) await _client.DisposeAsync();
        }
    }
}
