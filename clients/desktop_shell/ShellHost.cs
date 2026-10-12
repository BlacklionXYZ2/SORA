using System.Runtime.InteropServices;
using Microsoft.Win32;
using Sora.DesktopWidget;
using Sora.DesktopApp;

namespace Sora.DesktopShell;

// One profile host owns presence; panel visibility never owns a service lifetime.
internal sealed class ShellHost : ApplicationContext
{
    private readonly ShellSession session;
    private readonly ShellInstance instance;
    private readonly ShellCoreCoordinator core;
    private readonly Control dispatch = new();
    private readonly CancellationTokenSource lifetime = new();
    private readonly System.Windows.Forms.Timer refresh = new() { Interval = 2000 };
    private readonly System.Windows.Forms.Timer delayedQuit = new() { Interval = 250 };
    private readonly NotifyIcon tray;
    private readonly ContextMenuStrip menu = new();
    private readonly Task pipeTask;
    private HotkeyWindow hotkey;
    private readonly ShellPreferencesStore preferences;
    private readonly Dictionary<string, PanelPreferencesBinding> bindings = [];
    private ShellShortcut registeredShortcut;
    private ShellForm? chat;
    // WebView2 GUI rewrite (W4, W5): panels listed here open as web pages from clients/panels/ unless
    // SORA_PANELS=classic; the rest keep their WinForms windows until their pages exist.
    private static readonly bool WebPanels = Environment.GetEnvironmentVariable("SORA_PANELS") != "classic";
    private static readonly IReadOnlyDictionary<string, Size> WebPages = new Dictionary<string, Size>
    {
        ["chat"] = new(480, 560), ["settings"] = new(980, 680), ["activity"] = new(960, 660),
        ["voice"] = new(840, 530), ["agents"] = new(820, 740), ["paths"] = new(1000, 670),
        ["memory"] = new(1060, 740), ["appearance"] = new(600, 640),
    };
    private static bool WebMemory => WebPanels && WebPages.ContainsKey("memory");
    private readonly Dictionary<string, WebPanelForm> webPanels = [];
    private PanelApiProxy? panelProxy;
    private SettingsForm? settings;
    private CommandMenuForm? commands;
    private AppearanceForm? appearance;
    private ActivityForm? activity;
    private VoicePanel? voice;
    private MemoryForm? memory;
    private AgentCatalogueForm? agents;
    private ProjectPathsForm? paths;
    private KanbanBoardForm? board;
    private RetainedBrowserForm? content, integrations;
    private bool PendingSecondaryWork => session.SecondaryMutationBusy || session.MemoryPresentationBusy || settings?.HasPendingWork == true || voice?.HasPendingWork == true || agents?.HasPendingWork == true || paths?.HasPendingWork == true
        || board?.HasPendingWork == true || content?.HasPendingWork == true || integrations?.HasPendingWork == true || memory?.HasPendingWork == true
        || webPresenting || PendingWebPanel() is not null;
    private bool webPresenting;
    // memoryGeneration when the Memory page's report arrived; a later change makes that report stale.
    private long? presentedGeneration;
    private bool webCoreUsable;
    private bool quitting;
    private bool quitPending;
    private bool resourcesDisposed;
    private long memoryGeneration;

    public ShellHost(ShellSession session, ShellInstance instance, ShellOptions options, ShellCoreCoordinator core)
    {
        this.session = session; this.instance = instance; this.core = core;
        session.EnableVoice();
        session.EnableMemoryPresentation(instance.ProfileKey, () => memoryGeneration, PresentMemoryAsync,
            (request, confirmed) => {
                if (WebMemory) webPanels.GetValueOrDefault("memory")?.Post(new {
                    type = "host.presentation-outcome", requestId = request.Request, confirmed });
                else memory?.SetPresentationOutcome(request, confirmed);
            });
        preferences = new ShellPreferencesStore(options.StateRoot!, options.LegacyWidgetFile, options.LegacyDesktopFile);
        ShellTheme.Palette = preferences.Current.Theme;
        dispatch.CreateControl(); _ = dispatch.Handle;
        menu.Items.Add("Chat", null, (_, _) => ShowPanel("chat"));
        menu.Items.Add("Voice / microphone", null, (_, _) => ShowPanel("voice"));
        menu.Items.Add("Memory / retained context", null, (_, _) => ShowPanel("memory"));
        menu.Items.Add("Activity / task evidence", null, (_, _) => ShowPanel("activity"));
        menu.Items.Add("Agents / delegate task", null, (_, _) => ShowPanel("agents"));
        menu.Items.Add("Project paths / writers", null, (_, _) => ShowPanel("paths"));
        menu.Items.Add("Note board", null, (_, _) => ShowPanel("board"));
        menu.Items.Add("Content / registered references", null, (_, _) => ShowPanel("content"));
        menu.Items.Add("Integrations / details", null, (_, _) => ShowPanel("integrations"));
        menu.Items.Add("Settings / recovery", null, (_, _) => ShowPanel("settings"));
        menu.Items.Add("Appearance / panels", null, (_, _) => ShowPanel("appearance"));
        menu.Items.Add("Command menu", null, (_, _) => ShowPanel("menu"));
        menu.Items.Add("Reconnect / retry startup", null, async (_, _) => await RetryCoreAsync());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Quit SORA", null, (_, _) => QueueNativeQuit());
        tray = new NotifyIcon { Icon = SystemIcons.Application, Visible = true,
            Text = "SORA · Core connecting · attached profile", ContextMenuStrip = menu };
        tray.DoubleClick += (_, _) => ShowPanel("chat");
        session.Changed += SessionChanged;
        core.Changed += CoreChanged;
        registeredShortcut = preferences.Current.Shortcut;
        hotkey = new HotkeyWindow(() => ShowPanel("chat"), registeredShortcut);
        preferences.Changed += PreferencesChanged;
        SystemEvents.DisplaySettingsChanged += DisplaySettingsChanged;
        SystemEvents.UserPreferenceChanged += UserPreferenceChanged;
        refresh.Tick += async (_, _) => await RefreshAsync();
        delayedQuit.Tick += async (_, _) => { delayedQuit.Stop(); await QuitAsync(); };
        pipeTask = Task.Run(() => instance.ServeAsync(DispatchAsync, lifetime.Token));
        refresh.Start();
        if (options.Panel is "chat" or "voice" or "memory" or "settings" or "appearance" or "activity" or "agents" or "paths" or "board" or "content" or "integrations" or "menu") ShowPanel(options.Panel);
        CoreChanged(null, EventArgs.Empty); _ = RetryCoreAsync();
    }
    private Task<bool> DispatchAsync(HostCommand command)
    {
        var result = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        try
        {
            dispatch.BeginInvoke(() => {
                if (quitting || !command.Valid(instance.ProfileKey)) { result.TrySetResult(false); return; }
                if (command.Panel == "quit")
                {
                    // Managed Quit needs a foreground consequence decision, not
                    // a modal spawned by a bounded secondary IPC request.
                    if (quitPending || core.HasOwnedLaunch || core.Options.Managed is not null && core.Phase == "starting"
                        || session.Sending || session.MutationBusy || PendingSecondaryWork || appearance?.HasUnsavedChanges == true || settings?.HasUnsavedChanges == true || memory?.HasUnsavedChanges == true
                        || webPanels.Values.Any(web => !web.IsDisposed && web.HasUnsavedChanges))
                    { result.TrySetResult(false); return; }
                    settings?.SetShutdownPending(true); delayedQuit.Start(); result.TrySetResult(true); return;
                }
                ShowPanel(command.Panel); result.TrySetResult(true);
            });
        }
        catch (Exception error) when (error is InvalidOperationException or ObjectDisposedException)
        { result.TrySetResult(false); }
        return result.Task.WaitAsync(lifetime.Token);
    }
    private void ShowPanel(string panel) => ShowPanel(panel, null);

    private void ShowPanel(string panel, string? select)
    {
        if (quitting || panel == "none") return;
        if (WebPanels && WebPages.ContainsKey(panel))
        {
            var web = EnsureWebPanel(panel);
            if (web.WindowState == FormWindowState.Minimized) web.WindowState = FormWindowState.Normal;
            web.Show(); web.Activate();
            if (select is not null) web.Select(select);
        }
        else if (panel == "chat")
        {
            if (chat is null || chat.IsDisposed)
            {
                chat = new ShellForm(session, hosted: true, reconnect: RetryCoreAsync);
                chat.SettingsRequested += (_, _) => ShowPanel("settings");
                chat.ActivityRequested += (_, _) => ShowPanel("activity");
                chat.ActivityTaskRequested += async id => { ShowPanel("activity"); if (activity is not null) await activity.SelectTaskAsync(id); };
                chat.MemoryRequested += async (id, version) => {
                    try { await session.RequestMemoryPanelAsync(id, version, lifetime.Token); await RefreshAsync(); }
                    catch (Exception error) when (error is not OperationCanceledException || !lifetime.IsCancellationRequested) {
                        if (!quitting) MessageBox.Show(chat, "Exact Memory selection was not confirmed. No other record selected. " + error.Message, "SORA · Memory");
                    }
                };
                chat.AgentsRequested += (_, _) => ShowPanel("agents");
                chat.PathsRequested += (_, _) => ShowPanel("paths");
                chat.RetainedRequested += ShowPanel;
                chat.CompactChanged += compact => {
                    var values = preferences.Current;
                    preferences.TrySave(values with { ChatCompact = compact }, values.Revision, out _);
                    bindings.GetValueOrDefault("chat")?.CaptureNow();
                };
                chat.ApplyPreferences(preferences.Current); Bind(chat, "chat");
            }
            if (chat.WindowState == FormWindowState.Minimized) chat.WindowState = FormWindowState.Normal;
            chat.Show(); chat.Activate();
        }
        else if (panel == "voice")
        {
            if (voice is null || voice.IsDisposed) {
                voice = new VoicePanel(session); voice.SettingsRequested += (_, _) => ShowPanel("settings"); Bind(voice, "voice");
            }
            voice.Show(); voice.Activate();
        }
        else if (panel == "activity")
        {
            if (activity is null || activity.IsDisposed)
            { activity = new ActivityForm(session, RefreshAsync); Bind(activity, "activity"); }
            activity.Show(); activity.Activate();
        }
        else if (panel == "agents")
        {
            if (agents is null || agents.IsDisposed) {
                agents = new AgentCatalogueForm(session, hosted: true, editableTask: true, canUseCore: () => session.CanUseCore);
                Bind(agents, "agents");
            }
            agents.UpdateHostAvailability(session.CoreInstanceId); agents.Show(); agents.Activate();
        }
        else if (panel == "paths")
        {
            if (paths is null || paths.IsDisposed) {
                paths = new ProjectPathsForm(session, hosted: true, canUseCore: () => session.CanUseCore);
                Bind(paths, "paths");
            }
            paths.UpdateHostAvailability(session.CoreInstanceId); paths.Show(); paths.Activate();
        }
        else if (panel == "board")
        {
            session.EnableRetained();
            if (board is null || board.IsDisposed) {
                board = new KanbanBoardForm(session.RetainedApi, () => session.Retained,
                    async token => { await session.RefreshAsync(token); return session.Retained; }, session,
                    hosted: true, canUseCore: () => session.RetainedCurrent && !session.MutationBusy,
                    coreEpoch: () => session.CoreInstanceId);
                board.SetExpanded(preferences.Current.BoardExpanded, notify: false);
                board.ExpandedChanged += expanded => {
                    var values = preferences.Current;
                    preferences.TrySave(values with { BoardExpanded = expanded }, values.Revision, out _);
                    bindings.GetValueOrDefault("board")?.CaptureNow();
                };
                Bind(board, "board", board.RefreshBoardAppearance);
            }
            board.Render(session.Retained); board.Show(); board.Activate(); _ = RefreshAsync();
        }
        else if (panel is "content" or "integrations")
        {
            session.EnableRetained();
            var browser = panel == "content" ? content : integrations;
            if (browser is null || browser.IsDisposed) {
                browser = new RetainedBrowserForm(session, panel == "integrations", RefreshAsync);
                if (panel == "content") content = browser; else integrations = browser;
                Bind(browser, panel);
            }
            browser.Render(); browser.Show(); browser.Activate(); _ = RefreshAsync();
        }
        else if (panel == "memory")
        {
            EnsureMemoryPanel();
            if (memory is null) return;
            memory.Show(); memory.Activate(); memory.OnUserOpen();
        }
        else if (panel == "settings")
        {
            if (settings is null || settings.IsDisposed)
            { settings = new SettingsForm(session, RetryCoreAsync, ShowPanel); Bind(settings, "settings"); }
            settings.UpdateProjection(); settings.Show(); settings.Activate();
        }
        else if (panel == "appearance")
        {
            if (appearance is null || appearance.IsDisposed)
            { appearance = new AppearanceForm(preferences, ShortcutStatus, () => ResetPlacement(out _)); Bind(appearance, "appearance"); }
            appearance.Show(); appearance.Activate();
        }
        else if (panel == "menu")
        {
            if (commands is null || commands.IsDisposed)
            { commands = new CommandMenuForm(target => target == "quit" ? QuitFromMenuAsync()
                    : target == "retry" ? RetryFromMenuAsync()
                    : DispatchAsync(new HostCommand(1, instance.ProfileKey, target)), core.Options.Managed is not null || core.HasOwnedLaunch,
                    () => core.Status); Bind(commands, "menu"); }
            commands.Show(); commands.Activate();
        }
    }
    private WebPanelForm EnsureWebPanel(string panel)
    {
        if (webPanels.TryGetValue(panel, out var web) && !web.IsDisposed) return web;
        var options = core.Options;
        panelProxy ??= new PanelApiProxy(options.CoreUrl, options.TokenFile, () => session.CoreInstanceId);
        web = new WebPanelForm(panel, Path.Combine(AppContext.BaseDirectory, "panels"), panelProxy,
            options.StateRoot!, (next, chosen) => ShowPanel(next, chosen), WebPages[panel], WebCommand);
        web.SetTextScale(preferences.Current.TextScale);
        // The tray and the host's own view of Core follow what a page just changed (the microphone, a task).
        web.CorePosted += (_, _) => { if (!quitting) _ = RefreshAsync(); };
        if (panel == "memory") web.GeometryChanged += (_, _) => ++memoryGeneration;
        webPanels[panel] = web;
        Bind(web, panel);
        if (panel == "memory") ++memoryGeneration;
        return web;
    }
    // Host work a page asked for. Preferences and placement are host-local, never Core.
    private void WebCommand(WebPanelForm web, PanelCommand command)
    {
        if (quitting) return;
        void Result(bool ok, string error = "") => web.Post(new { type = "host.result", requestId = command.RequestId, ok, error });
        switch (command.Kind)
        {
            case PanelCommandKind.PreferencesSave or PanelCommandKind.PreferencesReload or PanelCommandKind.PreferencesRecover
                or PanelCommandKind.PlacementReset when web.PanelName != "appearance":
                Result(false, "Only the Appearance window changes these preferences.");
                break;
            case PanelCommandKind.Ready:
                web.Post(PreferencesMessage());
                web.Post(new { type = "host.core", canUseCore = session.CanUseCore });
                break;
            case PanelCommandKind.PreferencesSave:
                var latest = preferences.Current;
                // Compare in the page's own units (whole percent), so an odd stored scale is not a phantom conflict.
                var baseline = PanelAppearance.From(latest) == command.Baseline ? latest : command.Baseline!.ApplyTo(latest);
                var saved = preferences.TrySaveAppearance(command.Values!.ApplyTo(latest), baseline, out var saveError);
                Result(saved, saveError);
                break;
            case PanelCommandKind.PreferencesReload:
                preferences.Reload(); Result(true);
                break;
            case PanelCommandKind.PreferencesRecover:
                if (!preferences.ReadOnly) { Result(false, "UI preferences are readable; there is nothing to recover."); break; }
                Result(preferences.TryRecoverDefaults(out var recoverError), recoverError);
                break;
            case PanelCommandKind.PlacementReset:
                Result(ResetPlacement(out var resetError), resetError);
                break;
            case PanelCommandKind.MemoryHighlightCleared:
                if (web.PanelName == "memory") ++memoryGeneration;
                break;
            case PanelCommandKind.MemoryPresented:
                if (web.PanelName == "memory") presentedGeneration = memoryGeneration;
                break;
        }
    }
    private object PreferencesMessage()
    {
        var values = preferences.Current;
        var imported = values.Imports.Where(item => item.Status == "imported").ToArray();
        return new {
            type = "host.preferences", revision = values.Revision, readOnly = preferences.ReadOnly,
            diagnostic = preferences.Diagnostic, filePath = preferences.FilePath, shortcutStatus = ShortcutStatus(),
            values = PanelAppearance.From(values),
            legacy = new {
                attempted = values.ImportAttempted, imported = imported.Length,
                invalid = values.Imports.Any(item => item.Status == "invalid"),
                topmostNotApplied = imported.Any(item => item.AlwaysOnTop == true),
                quietOrTabRecorded = imported.Any(item => item.Quiet.HasValue || item.SelectedTab.HasValue),
                legacyChatHint = values.LegacyChat is not null,
            },
        };
    }
    private WebPanelForm? PendingWebPanel() => webPanels.Values.FirstOrDefault(web => !web.IsDisposed && web.HasPendingWork);
    private Task<bool> QuitFromMenuAsync()
    {
        return Task.FromResult(QueueNativeQuit());
    }
    private void EnsureMemoryPanel()
    {
        if (memory is not null && !memory.IsDisposed) return;
        memory = new MemoryForm(session);
        memory.PresentationChanged += (_, _) => ++memoryGeneration;
        Bind(memory, "memory"); ++memoryGeneration;
    }
    private Task<MemoryPanelAck> PresentMemoryAsync(MemoryPanelRequest request, CancellationToken token)
    {
        // Semantic navigation does not activate a window or take ownership of user focus.
        if (quitting || quitPending || settings?.HasPendingWork == true || agents?.HasPendingWork == true
            || board?.HasPendingWork == true || paths?.HasPendingWork == true || content?.HasPendingWork == true
            || integrations?.HasPendingWork == true || voice?.HasPendingWork == true
            || webPanels.Values.Any(web => !web.IsDisposed && web.HasPendingWork && web.PanelName != "memory"))
            return Task.FromResult(new MemoryPanelAck(request, "deferred", Math.Max(memoryGeneration, request.Generation)));
        if (WebMemory) return PresentWebMemoryAsync(request, token);
        EnsureMemoryPanel();
        return memory!.PresentAsync(request, () => memoryGeneration, token);
    }
    // The web Memory page's half of MemoryForm.PresentAsync: the host checks and reads, the page
    // selects and highlights, and the acknowledgement carries only what the page reports it shows.
    private async Task<MemoryPanelAck> PresentWebMemoryAsync(MemoryPanelRequest request, CancellationToken token)
    {
        var web = EnsureWebPanel("memory");
        MemoryPanelAck Outcome(string state) => new(request, state, Math.Max(memoryGeneration, request.Generation),
            !web.IsDisposed && web.Visible && web.WindowState != FormWindowState.Minimized);
        bool Allowed() => !quitting && !web.IsDisposed && session.CanUseCore && MemoryPanelClient.CanPresent(request,
            session.CoreInstanceId, web.HasUnsavedChanges, web.HasPendingWork
                || session.TaskControlBusy || session.SecondaryMutationBusy || session.VoiceBusy
                // Web Voice, Agents and Paths call Core directly, so the session does not see their work.
                || webPanels.Values.Any(other => other != web && !other.IsDisposed && other.HasPendingWork),
            web.Visible, web.WindowState == FormWindowState.Minimized, web.LastDismissal, DateTimeOffset.UtcNow);
        if (webPresenting || !Allowed()) return Outcome("deferred");
        var beforeGeneration = memoryGeneration;
        webPresenting = true;
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, token);
        bounded.CancelAfter(request.Expires - DateTimeOffset.UtcNow > TimeSpan.Zero
            ? request.Expires - DateTimeOffset.UtcNow : TimeSpan.FromMilliseconds(1));
        try
        {
            var value = await session.MemoryDetailAsync(request.Id, bounded.Token);
            if (!await session.MemoryPresentationPendingAsync(request, bounded.Token)) return Outcome("unavailable");
            bounded.Token.ThrowIfCancellationRequested();
            if (!Allowed() || beforeGeneration != memoryGeneration) return Outcome("deferred");
            if (value.Epoch != request.Epoch || value.Item.Id != request.Id || value.Item.Version != request.Version)
                return Outcome("unavailable");
            // The page judges "already visible" after this show, so the host remembers what was on screen.
            var wasVisible = web.Visible;
            if (!wasVisible) web.ShowPassive();
            presentedGeneration = null;
            var shown = await web.PresentMemoryAsync(request, bounded.Token);
            if (shown is not { Anchor: { } anchor } answer || answer.Status is not ("selected" or "already-visible")
                || presentedGeneration != memoryGeneration
                || !Allowed() || !web.Visible || web.WindowState == FormWindowState.Minimized)
            {
                web.Post(new { type = "host.presentation-outcome", requestId = request.Request, confirmed = false });
                return Outcome("unavailable");
            }
            return new(request, wasVisible ? answer.Status : "selected", Math.Max(memoryGeneration, request.Generation),
                true, request.Id, request.Version, new(anchor.X, anchor.Y, anchor.Width, anchor.Height));
        }
        catch (Exception error) when (error is not OperationCanceledException || !token.IsCancellationRequested)
        {
            web.Post(new { type = "host.presentation-outcome", requestId = request.Request, confirmed = false });
            return Outcome("unavailable");
        }
        finally { webPresenting = false; }
    }
    private Task<bool> RetryFromMenuAsync() { _ = RetryCoreAsync(); return Task.FromResult(true); }
    private bool QueueNativeQuit()
    {
        if (quitting || quitPending) return false;
        if (settings is not null && !settings.CanCloseForHostShutdown()) {
            ShowPanel("settings"); return false;
        }
        if (appearance is not null && !appearance.CanCloseForHostShutdown()) return false;
        if (memory is not null && !memory.CanCloseForHostShutdown()) { ShowPanel("memory"); return false; }
        foreach (var web in webPanels.Values.Where(item => !item.IsDisposed && item.HasUnsavedChanges).ToArray())
        {
            ShowPanel(web.PanelName);
            if (MessageBox.Show(web, web.DisplayName + " has changes you have not saved. Quit anyway and lose them?",
                "SORA · Unsaved changes", MessageBoxButtons.YesNo, MessageBoxIcon.Warning,
                MessageBoxDefaultButton.Button2) != DialogResult.Yes) return false;
        }
        if (PendingSecondaryWork) { ShowPendingSecondary(); return false; }
        if (session.MutationBusy) { ShowPanel(session.VoiceBusy ? "voice" : "activity"); return false; }
        if (session.Sending)
        {
            ShowPanel("chat");
            MessageBox.Show(chat, "A response is still pending. Stop it before Quit. Closing Chat only hides it.", "SORA");
            return false;
        }
        if ((core.Options.Managed is not null || core.HasOwnedLaunch) && MessageBox.Show(commands is { IsDisposed: false } ? commands : settings,
            "Quit SORA? Her brain (llama.cpp), Laya, her avatar, voice and Core all close. Running agent " +
            "tasks get Core's graceful cleanup first; anything still running after that is stopped. " +
            "A Core this host did not start is left running.",
            "SORA · Quit owned session", MessageBoxButtons.YesNo, MessageBoxIcon.Question,
            MessageBoxDefaultButton.Button2) != DialogResult.Yes) return false;
        settings?.SetShutdownPending(true); delayedQuit.Start(); return true;
    }
    private void Bind(Form form, string panel, Action? appearance = null)
    {
        if (bindings.Remove(panel, out var previous)) previous.Dispose();
        bindings[panel] = new PanelPreferencesBinding(form, panel, preferences, appearance);
    }
    private string ShortcutStatus() => registeredShortcut == ShellShortcut.None ? "Chat shortcut disabled; use the command menu."
        : hotkey.Registered ? "Chat shortcut active: " + registeredShortcut
        : "Chat shortcut unavailable (registration conflict); use the command menu.";
    private void PreferencesChanged(object? sender, EventArgs args)
    {
        if (quitting) return;
        var values = preferences.Current;
        if (values.Shortcut != registeredShortcut)
        {
            hotkey.Dispose(); registeredShortcut = values.Shortcut;
            hotkey = new HotkeyWindow(() => ShowPanel("chat"), registeredShortcut);
        }
        chat?.ApplyPreferences(values); SessionChanged(null, EventArgs.Empty);
        var message = PreferencesMessage();
        foreach (var web in webPanels.Values.Where(item => !item.IsDisposed)) { web.SetTextScale(values.TextScale); web.Post(message); }
        if (board is { IsDisposed: false } && board.IsExpanded != values.BoardExpanded)
            board.SetExpanded(values.BoardExpanded, notify: false);
    }
    private void ShowPendingSecondary()
    {
        if (PendingWebPanel() is { } web) { ShowPanel(web.PanelName); return; }
        if (webPresenting) { ShowPanel("memory"); return; }
        ShowPanel(settings?.HasPendingWork == true ? "settings" : memory?.HasPendingWork == true ? "memory" : voice?.HasPendingWork == true ? "voice" : board?.HasPendingWork == true ? "board" : content?.HasPendingWork == true ? "content"
            : integrations?.HasPendingWork == true ? "integrations" : paths?.HasPendingWork == true ? "paths" : "agents");
    }
    private bool ResetPlacement(out string error)
    {
        var values = preferences.Current;
        if (!preferences.TrySave(values with { Panels = [], LegacyChat = null }, values.Revision, out error)) return false;
        foreach (var binding in bindings.Values) binding.Restore(defaults: true);
        return true;
    }
    private void DisplaySettingsChanged(object? sender, EventArgs args)
    {
        if (quitting || dispatch.IsDisposed) return;
        try { dispatch.BeginInvoke(() => { if (!quitting) foreach (var binding in bindings.Values) binding.ClampToWorkArea(); }); }
        catch (Exception error) when (error is InvalidOperationException or ObjectDisposedException) { }
    }
    private void UserPreferenceChanged(object sender, UserPreferenceChangedEventArgs args)
    {
        if (quitting || dispatch.IsDisposed) return;
        try { dispatch.BeginInvoke(() => { if (!quitting) foreach (var binding in bindings.Values) binding.RefreshAppearance(); }); }
        catch (Exception error) when (error is InvalidOperationException or ObjectDisposedException) { }
    }
    private async Task RefreshAsync()
    {
        if (quitting) return;
        core.CheckChild();
        try { await session.RefreshAsync(lifetime.Token); }
        catch (OperationCanceledException) { }
    }
    private async Task RetryCoreAsync()
    {
        if (quitting || quitPending) return;
        await core.StartOrAttachAsync();
        await RefreshAsync();
    }
    private void CoreChanged(object? sender, EventArgs args)
    {
        commands?.UpdateHostState(core.Options.Managed is not null || core.HasOwnedLaunch, core.Status);
        session.SetHostStatus(core.Status, core.EffectsBlocked);
    }
    private void SessionChanged(object? sender, EventArgs args)
    {
        if (quitting) return;
        settings?.UpdateProjection();
        agents?.UpdateHostAvailability(session.CoreInstanceId); paths?.UpdateHostAvailability(session.CoreInstanceId);
        if (session.CanUseCore != webCoreUsable)
        {
            webCoreUsable = session.CanUseCore;
            foreach (var web in webPanels.Values.Where(item => !item.IsDisposed))
                web.Post(new { type = "host.core", canUseCore = webCoreUsable });
        }
        board?.Render(session.Retained); content?.Render(); integrations?.Render();
        var label = core.EffectsBlocked ? "Core " + core.Phase
            : !session.Snapshot.Connected ? "Core unavailable" : session.Snapshot.StatusLabel;
        var detail = preferences.Diagnostic.Length > 0 ? " · UI preferences need attention"
            : !hotkey.Registered && registeredShortcut != ShellShortcut.None ? " · shortcut unavailable" : "";
        var text = "SORA · " + session.MicrophoneLabel + " · " + label + detail;
        tray.Icon = session.VoiceCurrent && session.Voice?.MicrophoneOpen == true ? SystemIcons.Warning
            : !session.VoiceCurrent || session.Voice?.MicrophoneOpen is null ? SystemIcons.Question : SystemIcons.Application;
        tray.Text = text[..Math.Min(63, text.Length)];
    }
    private async Task QuitAsync()
    {
        if (quitting || quitPending) return;
        if (PendingSecondaryWork) { settings?.SetShutdownPending(false); ShowPendingSecondary(); return; }
        if (session.MutationBusy) { settings?.SetShutdownPending(false); ShowPanel(session.VoiceBusy ? "voice" : "activity"); return; }
        if (session.Sending) { settings?.SetShutdownPending(false); ShowPanel("chat"); return; }
        if (settings is { ShutdownPending: false } && !settings.CanCloseForHostShutdown()) { ShowPanel("settings"); return; }
        if (memory is not null && !memory.CanCloseForHostShutdown()) { ShowPanel("memory"); return; }
        settings?.SetShutdownPending(true);
        quitPending = true;
        // Graceful first; then anything this host launched that is still running is closed, so
        // Quit always ends llama.cpp, Laya, the avatar, voice and Core (owner request 2026-10-09).
        await core.QuitAsync(lifetime.Token);
        core.CloseEverything();
        quitting = true; refresh.Stop(); lifetime.Cancel();
        commands?.Close(); appearance?.Close(); settings?.CloseForHostShutdown(); agents?.CloseForHostShutdown(); paths?.CloseForHostShutdown();
        board?.CloseForHostShutdown(); content?.CloseForHostShutdown(); integrations?.CloseForHostShutdown(); memory?.CloseForHostShutdown();
        voice?.CloseForHostShutdown(); activity?.CloseForHostShutdown(); chat?.CloseForHostShutdown();
        foreach (var web in webPanels.Values) web.CloseForHostShutdown();
        panelProxy?.Dispose(); tray.Visible = false;
        ExitThread();
    }
    protected override void Dispose(bool disposing)
    {
        if (disposing && !resourcesDisposed)
        {
            resourcesDisposed = true;
            quitting = true; lifetime.Cancel(); session.Changed -= SessionChanged;
            core.Changed -= CoreChanged;
            preferences.Changed -= PreferencesChanged; SystemEvents.DisplaySettingsChanged -= DisplaySettingsChanged;
            SystemEvents.UserPreferenceChanged -= UserPreferenceChanged;
            refresh.Dispose(); delayedQuit.Dispose(); hotkey.Dispose();
            foreach (var binding in bindings.Values) binding.Dispose(); bindings.Clear();
            commands?.Dispose(); appearance?.Dispose(); settings?.Dispose(); agents?.Dispose(); paths?.Dispose();
            board?.Dispose(); content?.Dispose(); integrations?.Dispose(); memory?.Dispose();
            voice?.Dispose(); activity?.Dispose(); chat?.Dispose(); tray.Dispose(); menu.Dispose(); dispatch.Dispose();
            // Pipe I/O is cancelled, with no process/service kill. Observe failures rather than abandon them.
            try { pipeTask.GetAwaiter().GetResult(); } catch (OperationCanceledException) { }
            lifetime.Dispose();
        }
        base.Dispose(disposing);
    }

    private sealed class HotkeyWindow : NativeWindow, IDisposable
    {
        private readonly Action summon;
        public bool Registered { get; }
        public HotkeyWindow(Action summon, ShellShortcut shortcut)
        {
            this.summon = summon;
            CreateHandle(new CreateParams { Caption = "SORA host command target", Parent = new IntPtr(-3) });
            Registered = shortcut != ShellShortcut.None && RegisterHotKey(Handle, 1, 0x0001 | 0x0002 | 0x4000,
                (uint)(shortcut == ShellShortcut.CtrlAltS ? Keys.S : Keys.Space));
        }
        protected override void WndProc(ref Message message)
        {
            if (message.Msg == 0x0312 && message.WParam == new IntPtr(1)) summon();
            base.WndProc(ref message);
        }
        public void Dispose() { if (Registered) UnregisterHotKey(Handle, 1); DestroyHandle(); }
        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool RegisterHotKey(IntPtr window, int id, uint modifiers, uint key);
        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool UnregisterHotKey(IntPtr window, int id);
    }
}
