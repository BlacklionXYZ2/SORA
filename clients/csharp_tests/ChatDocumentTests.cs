using Sora.DesktopShell;

public sealed class ChatDocumentTests
{
    private static ChatDocument Document(params (string Id, string Text)[] entries)
    {
        var start = 0; var spans = new List<ChatSpan>();
        foreach (var entry in entries) { spans.Add(new(entry.Id, start, entry.Text)); start += entry.Text.Length; }
        return new(spans);
    }

    [Fact]
    public void ShiftedHistoryKeepsSelectionOnSameCanonicalMessage()
    {
        var before = Document(("old", "Older\n"), ("keep", "Heading\nΩ selected\n"), ("next", "Next\n"));
        var selection = before.CaptureSelection(14, 10);
        var after = Document(("keep", "Heading\nΩ selected\n"), ("next", "Next\n"), ("new", "New\n"));
        Assert.True(after.TryRestoreSelection(selection, out var start, out var length));
        Assert.Equal(8, start); Assert.Equal(10, length);
        Assert.Equal("Ω selected", string.Concat(after.Spans.Select(span => span.Text)).Substring(start, length));
    }

    [Fact]
    public void PrependingEarlierHistoryKeepsSelectionAndViewportIdentity()
    {
        var before = Document(("keep", "selected"), ("tail", "tail"));
        var after = Document(("earlier", "Earlier\n"), ("keep", "selected"), ("tail", "tail"));
        Assert.True(after.TryRestoreSelection(before.CaptureSelection(0, 8), out var start, out var length));
        Assert.Equal(8, start); Assert.Equal(8, length);
        Assert.Equal(10, after.Resolve(before.AnchorAt(2)));
    }

    [Fact]
    public void AppendingAtSelectionEndDoesNotSelectTheNextMessage()
    {
        var before = Document(("first", "whole")); var selection = before.CaptureSelection(0, 5);
        var after = Document(("first", "whole"), ("new", "new"));
        Assert.True(after.TryRestoreSelection(selection, out var start, out var length));
        Assert.Equal(0, start); Assert.Equal(5, length);
    }

    [Fact]
    public void DeletedSelectedMessageDoesNotSelectUnrelatedReplacement()
    {
        var before = Document(("gone", "selected"), ("keep", "remaining"));
        var after = Document(("keep", "remaining"));
        Assert.False(after.TryRestoreSelection(before.CaptureSelection(1, 4), out _, out _));
        Assert.Null(after.Resolve(new("gone", 2)));
        Assert.Equal(new ChatAnchor("keep", 0), after.SurvivingViewport(new("gone", 2), before));
    }

    [Theory]
    [InlineData("corrected")]
    [InlineData("x")]
    public void CorrectedTextClearsSelectionInsteadOfSelectingDifferentWords(string correction)
    {
        var before = Document(("same", "selected")); var after = Document(("same", correction));
        Assert.False(after.TryRestoreSelection(before.CaptureSelection(0, 4), out _, out _));
        Assert.Equal(Math.Min(7, correction.Length), after.Resolve(new("same", 7)));
    }

    [Fact]
    public void MissingMiddleMessageOrReorderingInvalidatesCrossMessageSelection()
    {
        var before = Document(("a", "aaa"), ("b", "bbb"), ("c", "ccc"));
        var selection = before.CaptureSelection(1, 7);
        Assert.False(Document(("a", "aaa"), ("c", "ccc")).TryRestoreSelection(selection, out _, out _));
        Assert.False(Document(("c", "ccc"), ("b", "bbb"), ("a", "aaa")).TryRestoreSelection(selection, out _, out _));
    }

    [Fact]
    public void DuplicateOrBlankIdsCannotAnchorAnotherRecord()
    {
        var duplicate = Document(("id", "first"), ("id", "second"));
        Assert.Null(duplicate.AnchorAt(1)); Assert.Null(duplicate.Resolve(new("id", 0)));
        Assert.Null(Document(("", "blank")).AnchorAt(0));
    }

    [Fact]
    public void EmptyDocumentAndUnmatchedViewportFallbackDoNotInventIdentity()
    {
        var empty = Document(); Assert.Null(empty.AnchorAt(0));
        Assert.Null(empty.CaptureSelection(0, 0));
        Assert.False(empty.TryRestoreSelection(null, out _, out _));
        var old = Document(("old", "old")); var current = Document(("new", "new"));
        Assert.Equal(new ChatAnchor("new", 0), current.SurvivingViewport(new("old", 1), old));
        Assert.Null(empty.SurvivingViewport(new("old", 1), old));
    }

    [Fact]
    public void UnicodeAndNativeLineEndingsUseActualUtf16Lengths()
    {
        var before = Document(("a", "first\r\n"), ("b", "😀Ω\r\ntext"));
        var after = Document(("b", "😀Ω\r\ntext"));
        Assert.True(after.TryRestoreSelection(before.CaptureSelection(7, 3), out var start, out var length));
        Assert.Equal(0, start); Assert.Equal(3, length);
        Assert.Equal(3, after.Resolve(before.AnchorAt(10)));
    }
}
