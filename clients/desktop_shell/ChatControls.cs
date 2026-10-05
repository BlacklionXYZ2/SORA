using System.Runtime.InteropServices;
using Sora.DesktopWidget;

namespace Sora.DesktopShell;

internal sealed class ChatComposer : TextBox
{
    private bool composing, commitPending;
    public bool CanSubmit(KeyEventArgs key) => ChatPresentation.ShouldSend(key.KeyCode == Keys.Enter,
        key.Shift, key.Control, key.Alt, composing, commitPending);
    protected override void WndProc(ref Message message)
    {
        if (message.Msg == 0x010D) { composing = true; commitPending = false; } // WM_IME_STARTCOMPOSITION
        if (message.Msg == 0x010E) { composing = false; commitPending = true; } // WM_IME_ENDCOMPOSITION
        base.WndProc(ref message);
    }
    protected override void OnKeyDown(KeyEventArgs key)
    {
        if (key.KeyCode != Keys.Enter && !composing) commitPending = false;
        base.OnKeyDown(key);
    }
    protected override void OnKeyUp(KeyEventArgs key)
    {
        base.OnKeyUp(key);
        if (key.KeyCode == Keys.Enter && !composing) commitPending = false;
    }
}

internal sealed class ChatTranscript : RichTextBox
{
    private IReadOnlyList<WidgetMessage> messages = Array.Empty<WidgetMessage>();
    private ChatDocument document = new([]);
    public event EventHandler? UnseenMessages;
    public ChatTranscript()
    {
        Dock = DockStyle.Fill; ReadOnly = true; BorderStyle = BorderStyle.None;
        DetectUrls = false; HideSelection = false; AccessibleName = "Conversation transcript";
        BackColor = ShellTheme.Surface; ForeColor = ShellTheme.Text;
    }

    public bool AtBottom => TextLength == 0 || GetCharIndexFromPosition(
        new Point(Math.Max(0, ClientSize.Width - 8), Math.Max(0, ClientSize.Height - 8))) >= TextLength - 3;

    public void JumpToLatest()
    { Select(TextLength, 0); ScrollToCaret(); }

    public void UpdateMessages(IReadOnlyList<WidgetMessage> next, bool restyle = false)
    {
        if (!restyle && messages.SequenceEqual(next)) return;
        var following = AtBottom;
        var selectionLength = SelectionLength;
        var selection = document.CaptureSelection(SelectionStart, selectionLength);
        var firstLine = SendMessage(Handle, 0x00CE, IntPtr.Zero, IntPtr.Zero).ToInt32(); // EM_GETFIRSTVISIBLELINE
        var firstChar = Math.Max(0, GetFirstCharIndexFromLine(firstLine));
        var viewport = document.AnchorAt(firstChar);
        var viewportY = GetPositionFromCharIndex(firstChar).Y;
        var previous = document;
        var scroll = new NativePoint(); SendMessage(Handle, 0x04DD, IntPtr.Zero, ref scroll); // EM_GETSCROLLPOS
        var append = !restyle && ChatPresentation.IsAppend(messages, next);
        var pending = next.Skip(append ? messages.Count : 0).ToArray();
        var changed = !messages.SequenceEqual(next);
        SendMessage(Handle, 0x000B, IntPtr.Zero, IntPtr.Zero); // WM_SETREDRAW
        try
        {
            if (!append) Clear();
            var spans = append ? document.Spans.ToList() : [];
            using var normal = new Font(Font.FontFamily, Font.Size, FontStyle.Regular);
            using var heading = new Font(Font.FontFamily, Font.Size, FontStyle.Bold);
            using var code = new Font("Consolas", Font.Size, FontStyle.Regular);
            foreach (var message in pending)
            {
                var start = TextLength;
                var entry = ChatPresentation.Entry(message);
                Select(TextLength, 0); SelectionFont = heading;
                SelectionColor = message.Role == "assistant" ? ShellTheme.Accent : ShellTheme.Secondary;
                AppendText(entry.Heading + "\n");
                foreach (var paragraph in entry.Paragraphs)
                {
                    SelectionFont = paragraph.Code ? code : normal; SelectionColor = ShellTheme.Text;
                    AppendText(paragraph.Text + "\n");
                }
                AppendText("\n");
                spans.Add(new(message.Id, start, Text[start..]));
            }
            messages = next.ToArray();
            document = new(spans);
            if (following && selectionLength == 0) JumpToLatest();
            else
            {
                if (document.TryRestoreSelection(selection, out var start, out var length)) Select(start, length);
                else Select(0, 0);
                if (append) SendMessage(Handle, 0x04DE, IntPtr.Zero, ref scroll); // EM_SETSCROLLPOS
                else if (document.Resolve(document.SurvivingViewport(viewport, previous)) is { } top)
                {
                    var current = new NativePoint(); SendMessage(Handle, 0x04DD, IntPtr.Zero, ref current);
                    current.Y = Math.Max(0, current.Y + GetPositionFromCharIndex(top).Y - viewportY);
                    SendMessage(Handle, 0x04DE, IntPtr.Zero, ref current);
                }
                if (changed) UnseenMessages?.Invoke(this, EventArgs.Empty);
            }
        }
        finally { SendMessage(Handle, 0x000B, new IntPtr(1), IntPtr.Zero); Invalidate(); }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativePoint { public int X, Y; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, ref NativePoint lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);
}
