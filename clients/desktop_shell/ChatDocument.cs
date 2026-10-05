namespace Sora.DesktopShell;

public sealed record ChatSpan(string Id, int Start, string Text)
{
    public int End => Start + Text.Length;
}
public sealed record ChatAnchor(string Id, int Offset);
public sealed record ChatSelection(ChatAnchor Start, ChatAnchor End, IReadOnlyList<ChatSpan> Messages);

// A process-local map of the rendered native document, never another history
// store. Measure actual RichEdit text rather than assuming newline lengths.
public sealed class ChatDocument(IReadOnlyList<ChatSpan> spans)
{
    public IReadOnlyList<ChatSpan> Spans { get; } = spans.ToArray();
    public int Length => Spans.Count == 0 ? 0 : Spans[^1].End;
    private ChatSpan? Unique(string id) => string.IsNullOrEmpty(id) ? null :
        Spans.Count(item => item.Id == id) == 1 ? Spans.First(item => item.Id == id) : null;

    public ChatAnchor? AnchorAt(int position, bool endBoundary = false)
    {
        if (Spans.Count == 0) return null;
        position = Math.Clamp(position, 0, Length);
        var span = endBoundary && position > 0
            ? Spans.FirstOrDefault(item => item.Start < position && position <= item.End)
            : Spans.FirstOrDefault(item => item.Start <= position && position < item.End);
        span ??= Spans[^1];
        return Unique(span.Id) is null ? null : new(span.Id, position - span.Start);
    }

    public int? Resolve(ChatAnchor? anchor)
    {
        if (anchor is null || Unique(anchor.Id) is not { } span) return null;
        return span.Start + Math.Clamp(anchor.Offset, 0, span.Text.Length);
    }

    public ChatSelection? CaptureSelection(int start, int length)
    {
        start = Math.Clamp(start, 0, Length);
        var end = start + Math.Clamp(length, 0, Length - start);
        var first = AnchorAt(start); var last = AnchorAt(end, endBoundary: end > start);
        if (first is null || last is null) return null;
        var selected = Spans.Where(span => span.End > start && span.Start < end).ToArray();
        return new(first, last, selected);
    }

    public bool TryRestoreSelection(ChatSelection? selection, out int start, out int length)
    {
        start = length = 0;
        if (selection is null || Resolve(selection.Start) is not { } first ||
            Resolve(selection.End) is not { } last || last < first) return false;
        // A correction/deletion/reorder must not select unrelated replacement
        // text merely because a previous absolute character offset still fits.
        var selected = Spans.Where(span => span.End > first && span.Start < last).ToArray();
        if (selected.Length != selection.Messages.Count || selected.Where((span, index) =>
            span.Id != selection.Messages[index].Id || span.Text != selection.Messages[index].Text).Any()) return false;
        start = first; length = last - first; return true;
    }

    public ChatAnchor? SurvivingViewport(ChatAnchor? anchor, ChatDocument previous)
    {
        if (Resolve(anchor) is not null) return anchor;
        if (anchor is null) return Spans.Count == 0 ? null : AnchorAt(0);
        var old = previous.Spans.ToList().FindIndex(span => span.Id == anchor.Id);
        // Prefer the next surviving old message, then a previous one. This is
        // viewport fallback only; deleted selections are always cleared.
        foreach (var span in previous.Spans.Skip(Math.Max(0, old + 1)).Concat(
            previous.Spans.Take(Math.Max(0, old)).Reverse()))
            if (Unique(span.Id) is not null) return new(span.Id, 0);
        return Spans.Count == 0 ? null : AnchorAt(0);
    }
}
