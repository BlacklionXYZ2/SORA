using Sora.DesktopWidget;

namespace Sora.DesktopShell;

public sealed record ChatAttachment(Guid Id, string Path, string Label);
public sealed record ChatParagraph(string Text, bool Code);
public sealed record ChatEntry(string Id, string Speaker, string Timestamp, IReadOnlyList<ChatParagraph> Paragraphs)
{
    public string Heading => Speaker + " · " + Timestamp;
    public string PlainText => Heading + "\n" + string.Join("\n", Paragraphs.Select(line => line.Text)) + "\n\n";
}

// Inert text/code projection. HTML, images, URLs and file names never become
// executable markup or window commands. Unsupported Markdown stays readable.
public static class ChatPresentation
{
    public static ChatEntry Entry(WidgetMessage message) => new(message.Id,
        message.Role switch { "assistant" => "SORA", "user" => "You", _ => message.Role },
        message.CreatedAt.ToLocalTime().ToString("g"),
        ChatText.Lines(message.Content).Select(line => new ChatParagraph(line.Text, line.Code)).ToArray());

    public static bool IsAppend(IReadOnlyList<WidgetMessage> before, IReadOnlyList<WidgetMessage> after) =>
        before.Count <= after.Count && before.SequenceEqual(after.Take(before.Count));

    public static bool ShouldSend(bool enter, bool shift, bool control, bool alt, bool composing, bool commitPending) =>
        enter && !shift && !control && !alt && !composing && !commitPending;
}
