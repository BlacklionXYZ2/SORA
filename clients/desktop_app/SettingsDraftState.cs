using System.Text.Json;

namespace Sora.DesktopApp;

// Only ephemeral edit state. Values and persistence remain owned by canonical Core.
public sealed class SettingsDraftState
{
    public static IReadOnlyDictionary<string, JsonElement> ReconciledValues(
        IReadOnlyDictionary<string, JsonElement> previous,
        IReadOnlyDictionary<string, JsonElement> current,
        IReadOnlyDictionary<string, JsonElement> edits)
    {
        if (previous.Keys.Any(key => !current.ContainsKey(key)) || edits.Keys.Any(key => !previous.ContainsKey(key)))
            throw new InvalidDataException("Draft field identity changed; reconciliation unavailable.");
        var values = current.ToDictionary(pair => pair.Key, pair => pair.Value.Clone());
        foreach (var (key, value) in edits) values[key] = value.Clone();
        return values;
    }
    public int Revision { get; private set; } = -1;
    public int Version { get; private set; }
    public string? Epoch { get; private set; }
    public bool Dirty { get; private set; }
    public bool Busy { get; private set; }
    public bool Conflict { get; private set; }
    public bool OutcomeUnknown { get; private set; }
    private long generation;
    public bool CanSave => Dirty && !Busy && !Conflict && !OutcomeUnknown && Version == 9;
    public bool Observe(int version, int revision, string? epoch)
    {
        if (version != 9 || revision < 0) { Conflict = true; return false; }
        if (Dirty || Busy) {
            Conflict = Version != version || Revision != revision || Epoch != epoch;
            return false;
        }
        bool rebuild = Version != version || Revision != revision || Epoch != epoch;
        Version = version; Revision = revision; Epoch = epoch; Conflict = OutcomeUnknown = false;
        return rebuild;
    }
    public void Edit() { Dirty = true; generation++; }
    public (long Generation, int Revision, string? Epoch) BeginSave()
    {
        if (!CanSave) throw new InvalidOperationException("Inspect current saved settings and reconcile the retained draft before saving.");
        Busy = true; return (generation, Revision, Epoch);
    }
    public (long Generation, int Revision, string? Epoch) BeginSave(string? currentEpoch)
    {
        if (Epoch != currentEpoch) throw new InvalidOperationException("Core changed; reconcile the retained draft before saving. Nothing submitted.");
        return BeginSave();
    }
    public bool Acknowledge((long Generation, int Revision, string? Epoch) submission,
        int version, int revision, string? epoch)
    {
        Busy = false;
        if (submission.Generation != generation || submission.Epoch != epoch || version != 9
            || revision < submission.Revision || revision > submission.Revision + 1) {
            OutcomeUnknown = true; return false;
        }
        Dirty = false; Revision = -1; Conflict = OutcomeUnknown = false; return true;
    }
    public void SaveFailed() { Busy = false; OutcomeUnknown = true; }
    public void Discard()
    {
        if (Busy) throw new InvalidOperationException("Wait for the pending settings operation.");
        Dirty = Conflict = OutcomeUnknown = false; Revision = -1; generation++;
    }
    public void Reconcile(int version, int revision, string? epoch, bool hasEdits)
    {
        if (Busy || version != 9 || revision < 0) throw new InvalidOperationException("A settled current canonical projection is required.");
        Version = version; Revision = hasEdits ? revision : -1; Epoch = epoch;
        Dirty = hasEdits; Conflict = OutcomeUnknown = false; generation++;
    }
}
