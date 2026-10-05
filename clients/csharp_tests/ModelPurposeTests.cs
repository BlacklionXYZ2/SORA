using System.Text.Json;
using Sora.DesktopWidget;

public sealed class ModelPurposeTests
{
    [Fact]
    public void DraftIsExactBoundedRoundTrippableAndDoesNotMutateItsSource()
    {
        var initial = JsonSerializer.SerializeToElement(new[] { new ModelPurposeRow("hermes:m1", "Research") });
        var draft = new ModelPurposeDraft(initial);
        draft.Upsert("hermes:m2", "Cheap docs");
        draft.Upsert("hermes:m1", "Updated purpose");
        Assert.Equal(1, initial.GetArrayLength());
        Assert.Equal(2, draft.Rows.Count);
        Assert.Equal("Updated purpose", draft.Rows[0].Purpose);
        Assert.Equal("hermes:m2", draft.ToJson()[1].GetProperty("id").GetString());
        Assert.True(draft.Remove("hermes:m1"));
        Assert.False(draft.Remove("unknown"));
        Assert.Single(new ModelPurposeDraft(draft.ToJson()).Rows);
    }

    [Fact]
    public void InvalidRowsAndOverflowDoNotPartiallyChangeTheDraft()
    {
        var draft = new ModelPurposeDraft(JsonSerializer.SerializeToElement(Array.Empty<object>()));
        Assert.Throws<ArgumentException>(() => draft.Upsert("two words", "x"));
        Assert.Throws<ArgumentException>(() => draft.Upsert("m", new string('x', 501)));
        Assert.Empty(draft.Rows);
        for (int index = 0; index < 64; index++) draft.Upsert("m" + index, "x");
        Assert.Throws<ArgumentException>(() => draft.Upsert("overflow", "x"));
        draft.Upsert("m0", "Still editable at limit");
        Assert.Equal(64, draft.Rows.Count);
        Assert.Throws<ArgumentException>(() => new ModelPurposeDraft(JsonSerializer.SerializeToElement(new[] {
            new ModelPurposeRow("m", "one"), new ModelPurposeRow("m", "two") })));
    }
}
