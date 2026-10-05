namespace Sora.DesktopWidget;

// Process-local intent, not another canonical board. Never replace a key after an uncertain reply.
public sealed class BoardNoteDraft
{
    public string Key { get; } = "board-plan-" + Guid.NewGuid().ToString("N");
    public string? Intent { get; private set; }
    public string? Assignee { get; private set; }
    public string? TaskId { get; private set; }
    public bool Confirmed { get; private set; }
    public string? Epoch { get; private set; }
    public void Begin(string intent, string assignee, string? epoch = null)
    {
        if (Confirmed) throw new InvalidOperationException("This note is already saved. Start a new note draft.");
        if (string.IsNullOrWhiteSpace(intent) || intent.Length > 4000 || assignee is not
            ("unassigned" or "sora" or "codex" or "claude" or "hermes" or "antigravity"))
            throw new ArgumentException("Enter a bounded note and known assignee.");
        if (Intent is not null && (Intent != intent || Assignee != assignee || Epoch != epoch))
            throw new InvalidOperationException("Unconfirmed note retained. Restore the submitted draft and explicitly retry; do not create duplicate work.");
        Intent = intent; Assignee = assignee; Epoch = epoch;
    }
    public void Acknowledge(string taskId)
    {
        _ = FullAppProjection.BoardPath(taskId, "assign");
        if (Intent is null || TaskId is not null && TaskId != taskId)
            throw new InvalidOperationException("Note acknowledgement identity mismatch; inspect the board.");
        TaskId = taskId;
    }
    public void Confirm()
    {
        if (TaskId is null) throw new InvalidOperationException("Note admission has not been confirmed.");
        Confirmed = true;
    }
}
