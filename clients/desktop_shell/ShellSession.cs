using System.Text.Json;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

// Shared presenter foundations. No new canonical store, inference client or automatic effect replay.
public sealed class ShellSession(IWidgetApi api, string? stateRoot = null, Action<string?>? bindInstance = null) : IDisposable, IAgentWorkflow
{
    private readonly WidgetSync sync = new(api);
    private readonly SemaphoreSlim refreshLock = new(1, 1);
    private bool disposed;
    private bool profileVerified = stateRoot is null;
    public string? CoreInstanceId { get; private set; }
    public event EventHandler? Changed;
    public WidgetSnapshot Snapshot => profileVerified ? sync.Current : sync.Current with { Connected = false,
        Error = SettingsError, DialogueReady = false };
    public JsonElement? Settings { get; private set; }
    public string SettingsError { get; private set; } = "Settings have not been read.";
    private string draft = "";
    private long draftRevision;
    private readonly List<ChatAttachment> attachments = [];
    public string Draft { get => draft; set {
        if (draft == value) return;
        draft = value; draftRevision++; Changed?.Invoke(this, EventArgs.Empty);
    } }
    public IReadOnlyList<ChatAttachment> Attachments => attachments.ToArray();
    public string HostStatus { get; private set; } = "";
    private bool hostEffectsBlocked;
    public string Operation { get; private set; } = stateRoot is null
        ? "GUI-0 prototype · existing clients remain unchanged."
        : "Profile host · closing Chat hides it; Quit follows explicit Core ownership.";
    public string? RequestId { get; private set; }
    public bool Sending => RequestId is not null;
    public bool CanUseCore => !disposed && !hostEffectsBlocked && Snapshot.Connected;
    public bool CanSend => CanUseCore && Snapshot.DialogueReady && !Sending;
    public bool TaskControlBusy { get; private set; }
    public bool SecondaryMutationBusy { get; private set; }
    public bool MutationBusy => TaskControlBusy || SecondaryMutationBusy || VoiceBusy || MemoryPresentationBusy;
    public bool MemoryPresentationBusy => memoryPanelClient?.Busy == true;
    public string MemoryPresentationStatus => memoryPanelClient?.Status ?? "Memory presentation not enabled.";
    private MemoryPanelClient? memoryPanelClient;
    private Func<long>? memoryGeneration;
    private Func<MemoryPanelRequest, CancellationToken, Task<MemoryPanelAck>>? presentMemory;
    private Action<MemoryPanelRequest, bool>? memorySettled;
    public void EnableMemoryPresentation(string profile, Func<long> generation,
        Func<MemoryPanelRequest, CancellationToken, Task<MemoryPanelAck>> present,
        Action<MemoryPanelRequest, bool>? settled = null)
    {
        if (stateRoot is null || memoryPanelClient is not null) throw new InvalidOperationException("A matching profile host is required.");
        memoryPanelClient = new(profile); memoryGeneration = generation; presentMemory = present; memorySettled = settled;
    }
    public bool VoiceBusy { get; private set; }
    public VoiceProjection? Voice { get; private set; }
    public string VoiceError { get; private set; } = "Voice status has not been read.";
    private bool voiceEnabled;
    private string? voiceEpoch;
    private int voiceReadRevision;
    public bool VoiceCurrent => CanUseCore && voiceEpoch == CoreInstanceId && Voice is not null && VoiceError.Length == 0;
    public string MicrophoneLabel => Voice?.MicrophoneLabel(VoiceCurrent) ?? "Mic status UNKNOWN";
    public void EnableVoice() => voiceEnabled = true;
    private readonly Dictionary<string, (string? Epoch, JsonElement Body)> submissions = [];
    private readonly Dictionary<string, (string? Epoch, JsonElement Body)> boardPlans = [];
    private readonly HashSet<string> uncertainBoardRetries = [];
    private bool retainedEnabled;
    private FullAppSnapshot retained = FullAppSnapshot.Empty;
    private string? retainedEpoch;
    private string retainedError = "Retained projections have not been read.";
    public bool RetainedCurrent => CanUseCore && retainedEpoch == CoreInstanceId && retainedError.Length == 0;
    public FullAppSnapshot Retained => retained with { Companion = Snapshot with { Connected = RetainedCurrent }, Error = retainedError };
    public void EnableRetained() => retainedEnabled = true;
    private IWidgetApi? retainedApi;
    public IWidgetApi RetainedApi => retainedApi ??= new RetainedApi(this);
    private IWidgetApi? settingsApi;
    public IWidgetApi SettingsApi => settingsApi ??= new SettingsApi(this);
    private string? settingsEpoch;
    private int settingsReadRevision;
    public bool SettingsCurrent => CanUseCore && settingsEpoch == CoreInstanceId && Settings.HasValue && SettingsError.Length == 0;

    public Task<JsonElement> SettingsOperationAsync(string path, object request, CancellationToken token)
    {
        var body = JsonSerializer.SerializeToElement(request);
        if (path == "/api/v1/agents/catalogue/refresh") {
            if (body.ValueKind != JsonValueKind.Object || body.EnumerateObject().Any())
                throw new ArgumentException("Use an empty catalogue refresh request.");
            return AgentCatalogueAsync(true, token);
        }
        if (path == "/api/v1/models/projectors") {
            if (body.ValueKind != JsonValueKind.Object || body.EnumerateObject().Count() != 1
                || !body.TryGetProperty("model_path", out var model) || model.ValueKind != JsonValueKind.String
                || model.GetString() is not { Length: > 0 and <= 2048 })
                throw new ArgumentException("Choose an exact bounded local GGUF path.");
            return SecondaryReadAsync(() => api.PostAsync(path, body, token));
        }
        if (path is not ("/api/v1/settings" or "/api/v1/settings/refresh" or "/api/v1/model/reload"))
            throw new NotSupportedException("Unsupported settings route.");
        var epoch = CoreInstanceId;
        return SecondaryMutationAsync(async () => {
            async Task VerifyIdentityAsync() {
                CheckSecondaryEpoch(epoch);
                if (stateRoot is null) return;
                var identity = await api.GetAsync("/api/v1/runtime/identity", token);
                if (ShellProfile.ValidateIdentity(identity, stateRoot) != epoch)
                    throw new InvalidOperationException("Core identity changed; inspect Settings before another effect.");
                CheckSecondaryEpoch(epoch);
            }
            await VerifyIdentityAsync();
            var current = await api.GetAsync("/api/v1/projections/settings", token); CheckSecondaryEpoch(epoch);
            SettingsRequests.Validate(path, body, current);
            var before = SettingsRequests.Projection(current);
            ++settingsReadRevision;
            try {
                var reply = await api.PostAsync(path, body, token); CheckSecondaryEpoch(epoch, mutation: true);
                await VerifyIdentityAsync();
                var after = SettingsRequests.Projection(reply);
                if (path == "/api/v1/settings" && (after.Revision < before.Revision || after.Revision > before.Revision + 1)
                    || path == "/api/v1/model/reload" && after.Revision != before.Revision)
                    throw new InvalidDataException("Settings acknowledgement revision mismatch; outcome unknown.");
                Settings = reply.Clone(); settingsEpoch = epoch; SettingsError = ""; return reply;
            }
            catch { SettingsError = "Settings effect unconfirmed; inspect saved state. No automatic retry."; throw; }
            finally { ++settingsReadRevision; }
        });
    }

    private async Task ReadRetainedAsync(CancellationToken token)
    {
        var epoch = CoreInstanceId;
        try {
            var board = api.GetAsync("/api/v1/projections/objects", token);
            var content = api.GetAsync("/api/v1/content/references", token);
            var extensions = api.GetAsync("/api/v1/extensions", token);
            var capabilities = api.GetAsync("/api/v1/projections/capabilities", token);
            await Task.WhenAll(board, content, extensions, capabilities); CheckSecondaryEpoch(epoch);
            RetainedRequests.ValidateProjectionShapes(await board, await content, await extensions, await capabilities);
            var cards = FullAppProjection.ParseBoard(await board);
            var references = FullAppProjection.ParseContent(await content);
            var integrations = FullAppProjection.ParseExtensions(await extensions);
            retained = FullAppSnapshot.Empty with { BoardCards = cards, Content = references,
                Extensions = integrations, ActiveExtensions = FullAppProjection.ActiveExtensions(await capabilities), Error = "" };
            retainedEpoch = epoch; retainedError = "";
        }
        catch (Exception error) when (error is not OperationCanceledException || !token.IsCancellationRequested)
        { retainedError = "Retained board/content/integration data is stale or unavailable. " + error.Message; }
    }

    public async Task<JsonElement> MutateRetainedAsync(string path, object request, CancellationToken token)
    {
        var body = JsonSerializer.SerializeToElement(request);
        var target = RetainedRequests.Validate(path, body);
        if (!CanUseCore || MutationBusy) throw new InvalidOperationException("Retained action unavailable; nothing sent.");
        var epoch = CoreInstanceId;
        // Version and registered-target revalidation happen inside the serialized effect slot.
        return await SecondaryMutationAsync(async () => {
            if (target.Action == "plan") {
                var key = body.GetProperty("idempotency_key").GetString()!;
                if (boardPlans.TryGetValue(key, out var old)) {
                    if (old.Epoch != epoch || !JsonElement.DeepEquals(old.Body, body))
                        throw new InvalidOperationException("Retained plan key belongs to another note/Core; inspect the board.");
                }
                else {
                    if (boardPlans.Count >= 128) throw new InvalidOperationException("Plan history is full for this host session.");
                    boardPlans.Add(key, (epoch, body));
                }
            }
            else if (path == "/api/v1/content/navigate") {
                var current = FullAppProjection.ParseContent(await api.GetAsync("/api/v1/content/references", token));
                CheckSecondaryEpoch(epoch);
                if (!current.Any(item => item.Id == target.Id)) throw new InvalidOperationException("Registered content target disappeared; nothing sent.");
            }
            else {
                var current = FullAppProjection.ParseBoard(await api.GetAsync("/api/v1/projections/objects", token));
                CheckSecondaryEpoch(epoch);
                var card = current.SingleOrDefault(item => item.Id == target.Id)
                    ?? throw new InvalidOperationException("Board target disappeared; nothing sent.");
                if (target.Action == "retry") {
                    if (card.Status is not ("failed" or "cancelled" or "interrupted")) throw new InvalidOperationException("Task is no longer retryable; nothing sent.");
                    if (uncertainBoardRetries.Contains(target.Id!))
                        throw new InvalidOperationException("Earlier retry outcome is unknown. Inspect task/run evidence; this non-idempotent retry cannot be replayed in this host session.");
                }
                else if (card.BoardVersion != body.GetProperty("expected_version").GetInt32())
                    throw new InvalidOperationException("Board changed. Refresh and inspect before another edit; nothing sent.");
            }
            CheckSecondaryEpoch(epoch);
            if (target.Action == "retry") {
                if (uncertainBoardRetries.Count >= 128) throw new InvalidOperationException("Unconfirmed retry history is full. Inspect task evidence before further admissions.");
                uncertainBoardRetries.Add(target.Id!);
            }
            var reply = await api.PostAsync(path, body, token); CheckSecondaryEpoch(epoch, mutation: true);
            if (target.Action == "plan") _ = TaskPresentation.Path(TaskPresentation.Text(reply, "task_id"));
            else if (path == "/api/v1/content/navigate") {
                _ = RetainedRequests.NavigationOutcome(reply, target.Id!);
            }
            else if (TaskPresentation.Text(reply, "task_id") != target.Id)
                throw new InvalidDataException("Board acknowledgement target mismatch; outcome unknown.");
            if (target.Action == "retry") uncertainBoardRetries.Remove(target.Id!);
            return reply;
        });
    }

    private void CheckSecondaryEpoch(string? epoch, bool mutation = false)
    {
        if (!CanUseCore || CoreInstanceId != epoch)
            throw new InvalidOperationException(mutation
                ? "Core changed/disconnected after submission; outcome not confirmed. No automatic retry."
                : "Core changed/disconnected; retained evidence is stale.");
    }
    private async Task<JsonElement> SecondaryReadAsync(Func<Task<JsonElement>> read)
    {
        if (!CanUseCore) throw new InvalidOperationException("Connect the matching Core before reading this surface.");
        var epoch = CoreInstanceId; var result = await read(); CheckSecondaryEpoch(epoch); return result;
    }
    private async Task ReadVoiceAsync(CancellationToken token)
    {
        var epoch = CoreInstanceId; var revision = ++voiceReadRevision;
        try {
            var data = VoiceProjection.Parse(await sync.VoiceStatusAsync(token));
            CheckSecondaryEpoch(epoch);
            if (revision != voiceReadRevision) return;
            Voice = data; voiceEpoch = epoch; VoiceError = "";
        }
        catch (Exception error) when (error is not OperationCanceledException || !token.IsCancellationRequested) {
            if (revision == voiceReadRevision) VoiceError = "Voice status unavailable/last-known stale. " + error.Message;
        }
    }
    public async Task VoiceActionAsync(string action, CancellationToken token, string? expectedEpoch = null)
    {
        if (action is not ("start" or "begin" or "end" or "stop" or "stop_output" or "close"))
            throw new ArgumentException("Choose an exact supported voice action.");
        if (!CanUseCore || expectedEpoch is not null && expectedEpoch != CoreInstanceId
            || VoiceBusy || (action is "start" or "begin") && MutationBusy)
            throw new InvalidOperationException("Voice operation unavailable; nothing sent.");
        var epoch = CoreInstanceId; ++voiceReadRevision; VoiceBusy = true;
        VoiceError = "Voice operation pending; microphone status is unconfirmed."; Changed?.Invoke(this, EventArgs.Empty);
        try {
            var current = VoiceProjection.Parse(await sync.VoiceStatusAsync(token)); CheckSecondaryEpoch(epoch);
            if (!current.Can(action)) throw new InvalidOperationException("Voice state/policy changed; nothing sent.");
            var data = VoiceProjection.Parse(await sync.VoiceActionAsync(action, token), current.Enabled);
            CheckSecondaryEpoch(epoch, mutation: true); ++voiceReadRevision;
            Voice = data; voiceEpoch = epoch; VoiceError = "";
        }
        catch (Exception error) {
            ++voiceReadRevision; VoiceError = "Voice action not confirmed; no automatic retry. " + error.Message; throw;
        }
        finally { VoiceBusy = false; Changed?.Invoke(this, EventArgs.Empty); }
    }
    private async Task<JsonElement> SecondaryMutationAsync(Func<Task<JsonElement>> mutate)
    {
        if (!CanUseCore || MutationBusy) throw new InvalidOperationException("Core effects unavailable or another task/settings operation is pending; nothing sent.");
        var epoch = CoreInstanceId; SecondaryMutationBusy = true; Changed?.Invoke(this, EventArgs.Empty);
        try { var result = await mutate(); CheckSecondaryEpoch(epoch, mutation: true); return result; }
        finally { SecondaryMutationBusy = false; Changed?.Invoke(this, EventArgs.Empty); }
    }

    public Task<JsonElement> AgentCatalogueAsync(bool refresh = false, CancellationToken cancellationToken = default) =>
        refresh ? SecondaryMutationAsync(() => sync.AgentCatalogueAsync(true, cancellationToken))
            : SecondaryReadAsync(() => sync.AgentCatalogueAsync(false, cancellationToken));
    public Task<JsonElement> SettingsAsync(CancellationToken cancellationToken = default) =>
        SecondaryReadAsync(() => sync.SettingsAsync(cancellationToken));
    public Task<JsonElement> SaveModelPurposesAsync(int version, int revision, string agent, JsonElement rows,
        CancellationToken cancellationToken = default) =>
        SecondaryMutationAsync(() => sync.SaveModelPurposesAsync(version, revision, agent, rows, cancellationToken));
    public Task<JsonElement> ProjectPathsAsync(bool reconcile = false, CancellationToken cancellationToken = default) =>
        reconcile ? SecondaryMutationAsync(() => sync.ProjectPathsAsync(true, cancellationToken))
            : SecondaryReadAsync(() => sync.ProjectPathsAsync(false, cancellationToken));

    public async Task<JsonElement> DelegateAsync(string intent, string? referenceId, CancellationToken cancellationToken = default,
        AgentSelection? selection = null, string? idempotencyKey = null)
    {
        if (string.IsNullOrWhiteSpace(intent) || intent.Length > 8000 || string.IsNullOrWhiteSpace(idempotencyKey)
            || idempotencyKey.Length > 128 || idempotencyKey.Any(char.IsControl))
            throw new ArgumentException("A bounded explicit task and stable submission key are required.");
        if (!CanUseCore || MutationBusy) throw new InvalidOperationException("Task submission unavailable; nothing sent.");
        var body = JsonSerializer.SerializeToElement(AgentSelection.TaskBody(intent, referenceId, selection, idempotencyKey));
        if (submissions.TryGetValue(idempotencyKey, out var previous))
        {
            if (previous.Epoch != CoreInstanceId || !JsonElement.DeepEquals(previous.Body, body))
                throw new InvalidOperationException("Retained submission belongs to a different request/Core. Inspect Activity; do not resubmit it as new work.");
        }
        else
        {
            if (submissions.Count >= 128) throw new InvalidOperationException("Submission history is full for this host session; inspect Activity before restarting the host.");
            submissions.Add(idempotencyKey, (CoreInstanceId, body));
        }
        JsonElement result;
        try { result = await SecondaryMutationAsync(() => sync.DelegateAsync(intent, referenceId, cancellationToken, selection, idempotencyKey)); }
        catch (SoraRequestException error) when (error.Code == "INVALID_INPUT")
        { submissions.Remove(idempotencyKey); throw; } // This route validates INVALID_INPUT before task admission.
        // A transport acknowledgement alone does not prove execution/result.
        _ = TaskPresentation.Path(TaskPresentation.Text(result, "task_id"));
        return result;
    }
    public async Task<JsonElement> StartPlannedAsync(string taskId, string intent, AgentSelection selection,
        CancellationToken cancellationToken = default)
    {
        _ = TaskPresentation.Path(taskId);
        var result = await SecondaryMutationAsync(() => sync.StartPlannedAsync(taskId, intent, selection, cancellationToken));
        if (TaskPresentation.Text(result, "task_id") != taskId)
            throw new InvalidDataException("Planned-task acknowledgement identity mismatch; outcome not confirmed.");
        return result;
    }

    public async Task<JsonElement> TaskEvidenceAsync(string taskId, CancellationToken token)
    {
        var path = TaskPresentation.Path(taskId, "evidence");
        if (!CanUseCore) throw new InvalidOperationException("Connect the matching Core before reading task evidence.");
        var epoch = CoreInstanceId;
        var result = await api.GetAsync(path, token);
        if (!CanUseCore || CoreInstanceId != epoch) throw new InvalidOperationException("Core changed/disconnected; task evidence is not current.");
        if (TaskPresentation.Text(result.GetProperty("task"), "task_id") != taskId)
            throw new InvalidDataException("Task evidence identity mismatch.");
        return result;
    }

    public async Task<MemoryPageView> MemoryPageAsync(MemoryQuery query, string? cursor, CancellationToken token)
    {
        var epoch = CoreInstanceId;
        var result = await SecondaryReadAsync(() => api.GetAsync(query.Path(cursor), token));
        return MemoryPresentation.Page(result, query, epoch);
    }
    public async Task<MemoryDetailView> MemoryDetailAsync(string memoryId, CancellationToken token)
    {
        var epoch = CoreInstanceId;
        var result = await SecondaryReadAsync(() => api.GetAsync(MemoryPresentation.DetailPath(memoryId), token));
        return MemoryPresentation.Detail(result, memoryId, epoch);
    }
    public async Task<bool> MemoryPresentationPendingAsync(MemoryPanelRequest request, CancellationToken token)
    {
        if (CoreInstanceId != request.Epoch) return false;
        var result = await SecondaryReadAsync(() => api.GetAsync("/api/v1/ui/presentations/" + request.Request.ToString("D"), token));
        return MemoryPanelClient.StillPending(result, request);
    }
    public Task<JsonElement> RequestMemoryPanelAsync(string id, long version, CancellationToken token)
    {
        MemoryPresentation.ValidateId(id);
        if (version < 1 || CoreInstanceId is not { } epoch) throw new InvalidOperationException("Matching Core/version unavailable.");
        var request = Guid.NewGuid();
        return SecondaryMutationAsync(async () => {
            var result = await api.PostAsync("/api/v1/ui/present-memory", new { instance_id = epoch,
                request_id = request, memory_id = id, expected_version = version }, token);
            if (!MemoryPanelClient.StillPending(result, new(epoch, Guid.Empty, Guid.Empty, request, id, version, 0,
                "explicit", DateTimeOffset.UtcNow.AddSeconds(15))))
                throw new InvalidDataException("Owner Memory request was not queued; no success claimed.");
            Operation = "Memory selection requested · wait for host acknowledgement, not dispatch.";
            return result;
        });
    }

    public async Task<MemoryEditAck> EditMemoryAsync(MemoryMutationIntent intent, CancellationToken token)
    {
        intent.Validate();
        if (CoreInstanceId != intent.Epoch) throw new InvalidOperationException("Memory draft Core changed; nothing sent.");
        var result = await SecondaryMutationAsync(() => api.PostAsync(intent.Path, intent.Body(), token));
        return MemoryEditPresentation.Ack(result, intent, intent.Epoch);
    }
    public async Task<MemoryEditAck> MemoryReceiptAsync(MemoryMutationIntent intent, CancellationToken token)
    {
        intent.Validate(); var epoch = CoreInstanceId ?? throw new InvalidOperationException("Matching Core unavailable.");
        var result = await SecondaryReadAsync(() => api.GetAsync(intent.ReceiptPath, token));
        return MemoryEditPresentation.Ack(result, intent, epoch);
    }

    public async Task<JsonElement> TaskRunsAsync(string taskId, string? cursor, CancellationToken token)
    {
        var result = await SecondaryReadAsync(() => api.GetAsync(TaskPresentation.RunsPath(taskId, cursor: cursor), token));
        TaskPresentation.ValidateRuns(taskId, result); return result;
    }
    public async Task<JsonElement> TaskRunEvidenceAsync(string taskId, string runId, CancellationToken token)
    {
        var result = await SecondaryReadAsync(() => api.GetAsync(TaskPresentation.RunsPath(taskId, runId), token));
        TaskPresentation.ValidateRuns(taskId, result, runId); return result;
    }

    public async Task<JsonElement> ControlTaskAsync(string taskId, string action, string instruction, CancellationToken token)
    {
        var path = TaskPresentation.Path(taskId, action);
        if (action is not ("cancel" or "steer") || action == "steer" &&
            (string.IsNullOrWhiteSpace(instruction) || instruction.Length > 8000))
            throw new ArgumentException("Choose Cancel or a non-empty bounded steering instruction.");
        if (!CanUseCore || MutationBusy) throw new InvalidOperationException("Task control unavailable; nothing sent.");
        var epoch = CoreInstanceId;
        TaskControlBusy = true; Changed?.Invoke(this, EventArgs.Empty);
        try
        {
            // Re-read the captured exact ID immediately before mutation. The
            // responding Core is also fenced by the existing instance header.
            var current = await api.GetAsync(TaskPresentation.Path(taskId), token);
            if (!CanUseCore || CoreInstanceId != epoch || TaskPresentation.Text(current, "task_id") != taskId ||
                !TaskPresentation.CanControl(TaskPresentation.Text(current, "status"), action))
                throw new InvalidOperationException("Selected task is no longer controllable; nothing sent.");
            var result = await api.PostAsync(path, action == "steer" ? new { instruction } : (object)new { }, token);
            if (!CanUseCore || CoreInstanceId != epoch)
                throw new InvalidOperationException("Core changed/disconnected after task control; outcome not confirmed. No automatic retry.");
            if (TaskPresentation.Text(result, "task_id") != taskId)
                throw new InvalidDataException("Task control acknowledgement identity mismatch; outcome not confirmed.");
            return result;
        }
        finally { TaskControlBusy = false; Changed?.Invoke(this, EventArgs.Empty); }
    }

    public bool AddAttachment(string path)
    {
        if (disposed) throw new ObjectDisposedException(nameof(ShellSession));
        if (string.IsNullOrWhiteSpace(path) || path.Length > 4096 || path.Any(char.IsControl))
            throw new ArgumentException("Choose a readable local file path.");
        var full = Path.GetFullPath(path);
        if (attachments.Any(item => string.Equals(item.Path, full, StringComparison.OrdinalIgnoreCase))) return false;
        if (attachments.Count >= 3) throw new ArgumentException("Attach at most three files to a turn.");
        // Selection is metadata only. Core checks current existence/readability
        // and applies its bounded file/image handling at the explicit Send.
        attachments.Add(new(Guid.NewGuid(), full, Path.GetFileName(full)));
        Changed?.Invoke(this, EventArgs.Empty); return true;
    }

    public void RemoveAttachment(Guid id)
    {
        if (attachments.RemoveAll(item => item.Id == id) > 0) Changed?.Invoke(this, EventArgs.Empty);
    }

    public void SetHostStatus(string text, bool blockEffects)
    {
        HostStatus = text; hostEffectsBlocked = blockEffects;
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public async Task RefreshAsync(CancellationToken cancellationToken)
    {
        if (disposed) return;
        if (!await refreshLock.WaitAsync(0, cancellationToken)) return;
        try
        {
            if (stateRoot is not null)
            {
                profileVerified = false;
                try
                {
                    var identity = await api.GetAsync("/api/v1/runtime/identity", cancellationToken);
                    var instance = ShellProfile.ValidateIdentity(identity, stateRoot);
                    if (instance != CoreInstanceId) { sync.ResetForNewCore(); CoreInstanceId = instance;
                        Voice = null; VoiceError = "Core changed; voice status must be read again."; ++voiceReadRevision; }
                    bindInstance?.Invoke(instance); profileVerified = true;
                }
                catch (Exception error) when (error is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
                { SettingsError = "Core identity unavailable or mismatched. Cached data is stale. " + error.Message; return; }
            }
            await sync.RefreshAsync(cancellationToken);
            if (!Snapshot.Connected)
            {
                SettingsError = "Core unavailable. " + (Settings.HasValue ? "Last-known settings are stale." :
                    "No settings projection is available.");
                return;
            }
            var settingsRead = ++settingsReadRevision;
            var settingsCore = CoreInstanceId;
            try
            {
                var projection = await sync.SettingsAsync(cancellationToken); CheckSecondaryEpoch(settingsCore);
                if (settingsRead == settingsReadRevision && !SecondaryMutationBusy) {
                    Settings = projection; settingsEpoch = settingsCore; SettingsError = "";
                }
            }
            catch (Exception error) when (error is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
            { if (settingsRead == settingsReadRevision) SettingsError = "Settings unavailable; retained projection is stale. " + error.Message; }
            if (retainedEnabled) await ReadRetainedAsync(cancellationToken);
            if (voiceEnabled && !VoiceBusy) await ReadVoiceAsync(cancellationToken);
            if (CanUseCore && CoreInstanceId is { } memoryEpoch && memoryPanelClient is not null
                && memoryGeneration is not null && presentMemory is not null)
                await memoryPanelClient.RefreshAsync(api, memoryEpoch, memoryGeneration,
                    () => TaskControlBusy || SecondaryMutationBusy || VoiceBusy || !CanUseCore,
                    presentMemory, cancellationToken, memorySettled);
        }
        finally { refreshLock.Release(); Changed?.Invoke(this, EventArgs.Empty); }
    }

    public async Task SendAsync(CancellationToken cancellationToken)
    {
        if (!CanSend || string.IsNullOrWhiteSpace(Draft))
            throw new InvalidOperationException("Connect a ready dialogue model before sending.");
        var submitted = Draft;
        var submittedRevision = draftRevision;
        var submittedFiles = Attachments;
        RequestId = "shell-" + Guid.NewGuid().ToString("N");
        Operation = "Waiting for Core · whole-response API, no simulated token stream.";
        Changed?.Invoke(this, EventArgs.Empty);
        try
        {
            if (submittedFiles.Count == 0) await sync.DialogueAsync(submitted, cancellationToken, RequestId);
            else await sync.DialogueWithFilesAsync(submitted, submittedFiles.Select(item => item.Path).ToArray(),
                cancellationToken, RequestId);
            if (draftRevision == submittedRevision) Draft = "";
            var sentIds = submittedFiles.Select(item => item.Id).ToHashSet();
            attachments.RemoveAll(item => sentIds.Contains(item.Id));
            Operation = "Core returned a response. Check the canonical transcript.";
        }
        catch (Exception error)
        {
            Operation = error is SoraRequestException { Code: "DIALOGUE_CANCELLED" }
                ? "Response stopped. Draft retained; dispatched effects are not undone."
                : "Response not confirmed. Draft retained; no automatic retry. " + error.Message;
            throw;
        }
        finally { RequestId = null; Changed?.Invoke(this, EventArgs.Empty); }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        var request = RequestId;
        if (request is null) return;
        Operation = "Requesting Stop · dispatched effects are not undone.";
        try
        {
            var result = await sync.CancelDialogueAsync(request, cancellationToken);
            var state = result.GetProperty("state").GetString();
            Operation = state is "cancelling" or "cancelled" or "cancelled-before-start"
                ? "Core accepted Stop; waiting for the response to settle."
                : "Response already finishing; check the canonical transcript.";
        }
        catch (Exception error)
        { Operation = "Stop not confirmed. " + error.Message; throw; }
    }

    // Only managed async waits are used (never WaitHandle). Let the semaphore be collected:
    // cancelling a form can leave an awaited refresh releasing it after the form closes.
    public void Dispose() => disposed = true;
}
