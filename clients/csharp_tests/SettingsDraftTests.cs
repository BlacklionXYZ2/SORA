using Sora.DesktopApp;
using System.Text.Json;

public sealed class SettingsDraftTests
{
    [Theory]
    [InlineData("llama.model_path", "Models", false)]
    [InlineData("llama.speculative.draft_cache_type_k", "Models", true)]
    [InlineData("agents.hermes.project_root", "Tools", false)]
    [InlineData("agents.codex.model_choices", "Models", false)]
    [InlineData("local_companion.voice", "Audio", false)]
    [InlineData("local_companion.desktop_capture", "Vision", false)]
    [InlineData("runtime.worker_count", "Performance", false)]
    [InlineData("future.preference", "Advanced", false)]
    public void OlderCanonicalProjectionUsesTheSameCategoriesWithoutLosingUnknownFields(string key, string category, bool advanced)
    {
        var field = JsonSerializer.SerializeToElement(new { key });
        Assert.Equal(category, SettingsCategories.Category(field)); Assert.Equal(advanced, SettingsCategories.Advanced(field));
    }
    [Fact]
    public void ConflictingProjectionDoesNotReplaceDirtyBaseline()
    {
        var draft = new SettingsDraftState(); Assert.True(draft.Observe(10, 3, "core-a")); draft.Edit();
        Assert.False(draft.Observe(10, 4, "core-a")); Assert.True(draft.Dirty); Assert.True(draft.Conflict);
        Assert.Equal(3, draft.Revision); Assert.False(draft.CanSave);
        Assert.Throws<InvalidOperationException>(() => draft.BeginSave());
        draft.Discard(); Assert.True(draft.Observe(10, 4, "core-a")); draft.Edit(); Assert.True(draft.CanSave);
    }
    [Fact]
    public void CoreChangeWithSameRevisionIsStillConflict()
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "core-a"); draft.Edit();
        draft.Observe(10, 3, "core-b"); Assert.True(draft.Conflict); Assert.Equal("core-a", draft.Epoch);
    }
    [Fact]
    public void LateSaveCannotEraseEditsMadeDuringItsAwait()
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "core-a"); draft.Edit();
        var submission = draft.BeginSave(); Assert.True(draft.Busy); Assert.False(draft.CanSave);
        Assert.Throws<InvalidOperationException>(() => draft.Discard());
        draft.Edit(); Assert.False(draft.Acknowledge(submission, 10, 4, "core-a"));
        Assert.True(draft.Dirty); Assert.True(draft.OutcomeUnknown); Assert.False(draft.Busy);
    }
    [Theory]
    [InlineData(10, 3, "core-a", true)] [InlineData(10, 4, "core-a", true)]
    [InlineData(10, 2, "core-a", false)] [InlineData(10, 5, "core-a", false)]
    [InlineData(10, 4, "core-b", false)] [InlineData(9, 4, "core-a", false)]
    public void AcknowledgementIsBoundToExactSubmission(int version, int revision, string epoch, bool success)
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "core-a"); draft.Edit();
        Assert.Equal(success, draft.Acknowledge(draft.BeginSave(), version, revision, epoch));
        Assert.Equal(!success, draft.Dirty); Assert.Equal(!success, draft.OutcomeUnknown);
    }
    [Fact]
    public void FailedSaveRetainsDraftAndDoesNotAutomaticallyPermitRetry()
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "core-a"); draft.Edit(); draft.BeginSave(); draft.SaveFailed();
        draft.Observe(10, 3, "core-a"); Assert.True(draft.OutcomeUnknown); Assert.False(draft.CanSave);
        draft.Discard(); draft.Observe(10, 3, "core-a"); draft.Edit(); Assert.True(draft.CanSave);
    }
    [Fact]
    public void LegacySettingsCannotBeEdited()
    {
        var draft = new SettingsDraftState(); Assert.False(draft.Observe(8, 0, "core")); draft.Edit(); Assert.False(draft.CanSave);
    }
    [Fact]
    public void ExplicitReconciliationKeepsDraftAndChangesBaselineWithoutSaving()
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "old"); draft.Edit(); draft.BeginSave(); draft.SaveFailed();
        draft.Reconcile(10, 4, "new", true); Assert.True(draft.Dirty); Assert.True(draft.CanSave);
        Assert.Equal(4, draft.Revision); Assert.Equal("new", draft.Epoch); Assert.False(draft.OutcomeUnknown);
        Assert.False(draft.Observe(10, 4, "new")); Assert.False(draft.Conflict);
    }
    [Fact]
    public void ReconciliationCannotRunWhileSaveIsPendingOrAgainstLegacyState()
    {
        var draft = new SettingsDraftState(); draft.Observe(10, 3, "core"); draft.Edit(); draft.BeginSave();
        Assert.Throws<InvalidOperationException>(() => draft.Reconcile(10, 4, "core", true));
        draft.SaveFailed(); Assert.Throws<InvalidOperationException>(() => draft.Reconcile(8, 4, "core", true));
        draft.Reconcile(10, 4, "core", false); Assert.False(draft.Dirty); Assert.False(draft.CanSave);
    }
    [Fact]
    public void ReconciliationPreservesOnlyActualEditsAndAdoptsUntouchedConcurrentChanges()
    {
        static JsonElement J(int n) => JsonSerializer.SerializeToElement(n);
        var before = new Dictionary<string, JsonElement> { ["edited"] = J(1), ["untouched"] = J(2) };
        var now = new Dictionary<string, JsonElement> { ["edited"] = J(3), ["untouched"] = J(4), ["new"] = J(5) };
        var edits = new Dictionary<string, JsonElement> { ["edited"] = J(9) };
        var reviewed = SettingsDraftState.ReconciledValues(before, now, edits);
        Assert.Equal(9, reviewed["edited"].GetInt32()); Assert.Equal(4, reviewed["untouched"].GetInt32());
        Assert.Equal(5, reviewed["new"].GetInt32()); Assert.Equal(1, before["edited"].GetInt32());
        Assert.Equal(3, now["edited"].GetInt32());
        Assert.Throws<InvalidDataException>(() => SettingsDraftState.ReconciledValues(before,
            new Dictionary<string, JsonElement>(), edits));
        Assert.Throws<InvalidDataException>(() => SettingsDraftState.ReconciledValues(before, now,
            new Dictionary<string, JsonElement> { ["unknown"] = J(6) }));
    }
}
