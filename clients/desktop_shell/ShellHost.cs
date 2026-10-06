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
    // WebView2 GUI rewrite (W0): opt in with SORA_PANELS=web; the WinForms Chat stays the default.
    private static readonly bool WebPanels = Environment.GetEnvironmentVariable("SORA_PANELS") == "web";
    private WebPanelForm? webChat;
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
        || board?.HasPendingWork == true || content?.HasPendingWork == true || integrations?.HasPendingWork == true || memory?.HasPendingWork == true;
    private bool quitting;
    private bool quitPending;
    private bool resourcesDisposed;
    private long memoryGeneration;

    public ShellHost(ShellSession session, ShellInstance instance, ShellOptions options, ShellCoreCoordinator core)
    {
        this.session = session; this.instance = instance; this.core = core;
        session.EnableVoice();
        session.EnableMemoryPresentation(instance.ProfileKey, () => memoryGeneration, PresentMemoryAsync,
            (request, confirmed) => memory?.SetPresentationOutcome(request, confirmed));
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
        menu.Items.Add("Quit SORA (owned services only)", null, (_, _) => QueueNativeQuit());
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
                        || session.Sending || session.MutationBusy || PendingSecondaryWork || appearance?.HasUnsavedChanges == true || settings?.HasUnsavedChanges == true || memory?.HasUnsavedChanges == true)
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
    private void ShowPanel(string panel)
    {
        if (quitting || panel == "none") return;
        if (panel == "chat" && WebPanels)
        {
            if (webChat is null || webChat.IsDisposed)
            {
                var options = core.Options;
                panelProxy ??= new PanelApiProxy(options.CoreUrl, options.TokenFile, () => session.CoreInstanceId);
                webChat = new WebPanelForm("chat", Path.Combine(AppContext.BaseDirectory, "panels"), panelProxy,
                    options.StateRoot!, next => ShowPanel(next));
                Bind(webChat, "chat");
            }
            if (webChat.WindowState == FormWindowState.Minimized) webChat.WindowState = FormWindowState.Normal;
            webChat.Show(); webChat.Activate();
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
            { appearance = new AppearanceForm(preferences, ShortcutStatus, ResetPlacement); Bind(appearance, "appearance"); }
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
            || integrations?.HasPendingWork == true || voice?.HasPendingWork == true)
            return Task.FromResult(new MemoryPanelAck(request, "deferred", Math.Max(memoryGeneration, request.Generation)));
        EnsureMemoryPanel();
        return memory!.PresentAsync(request, () => memoryGeneration, token);
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
        if (PendingSecondaryWork) { ShowPendingSecondary(); return false; }
        if (session.MutationBusy) { ShowPanel(session.VoiceBusy ? "voice" : "activity"); return false; }
        if (session.Sending)
        {
            ShowPanel("chat");
            MessageBox.Show(chat, "A response is still pending. Stop it before Quit. Closing Chat only hides it.", "SORA");
            return false;
        }
        if ((core.Options.Managed is not null || core.HasOwnedLaunch) && MessageBox.Show(commands is { IsDisposed: false } ? commands : settings,
            "Quit this managed SORA session? External Core stays running. Only a Core this host launched " +
            "and its voice/avatar services will be closed. Existing tasks follow Core's graceful cleanup; this is not task cancellation. " +
            "If startup/cleanup cannot be confirmed, the host will remain available without force-killing services.",
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
        if (board is { IsDisposed: false } && board.IsExpanded != values.BoardExpanded)
            board.SetExpanded(values.BoardExpanded, notify: false);
    }
    private void ShowPendingSecondary()
    {
        ShowPanel(settings?.HasPendingWork == true ? "settings" : memory?.HasPendingWork == true ? "memory" : voice?.HasPendingWork == true ? "voice" : board?.HasPendingWork == true ? "board" : content?.HasPendingWork == true ? "content"
            : integrations?.HasPendingWork == true ? "integrations" : paths?.HasPendingWork == true ? "paths" : "agents");
    }
    private void ResetPlacement()
    {
        var values = preferences.Current;
        if (!preferences.TrySave(values with { Panels = [], LegacyChat = null }, values.Revision, out _)) return;
        foreach (var binding in bindings.Values) binding.Restore(defaults: true);
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
        if (!await core.QuitAsync(lifetime.Token))
        { quitPending = false; settings?.SetShutdownPending(false); ShowPanel("settings"); return; }
        quitting = true; refresh.Stop(); lifetime.Cancel();
        commands?.Close(); appearance?.Close(); settings?.CloseForHostShutdown(); agents?.CloseForHostShutdown(); paths?.CloseForHostShutdown();
        board?.CloseForHostShutdown(); content?.CloseForHostShutdown(); integrations?.CloseForHostShutdown(); memory?.CloseForHostShutdown();
        voice?.CloseForHostShutdown(); activity?.CloseForHostShutdown(); chat?.CloseForHostShutdown(); webChat?.CloseForHostShutdown();
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
