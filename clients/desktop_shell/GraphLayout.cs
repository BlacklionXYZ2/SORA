namespace Sora.DesktopShell;

public sealed record GraphNode(string Id, string Label);
public sealed record GraphEdge(string From, string To, string Evidence);
public sealed record PositionedNode(GraphNode Node, float X, float Y);
public sealed record GraphScene(IReadOnlyList<PositionedNode> Nodes, IReadOnlyList<GraphEdge> Edges,
    bool Truncated);

public static class GraphLayout
{
    public const int MaxNodes = 75;
    public static GraphScene Arrange(IEnumerable<GraphNode> source, IEnumerable<GraphEdge> relationships)
    {
        var bounded = source.Take(MaxNodes + 1).ToArray();
        if (bounded.Any(node => string.IsNullOrWhiteSpace(node.Id)) ||
            bounded.Select(node => node.Id).Distinct(StringComparer.Ordinal).Count() != bounded.Length)
            throw new ArgumentException("Graph nodes require unique nonempty IDs.");
        var nodes = bounded.Take(MaxNodes).OrderBy(node => node.Id, StringComparer.Ordinal).ToArray();
        var ids = nodes.Select(node => node.Id).ToHashSet(StringComparer.Ordinal);
        var columns = Math.Max(1, (int)Math.Ceiling(Math.Sqrt(nodes.Length)));
        var rows = Math.Max(1, (int)Math.Ceiling(nodes.Length / (double)columns));
        var placed = nodes.Select((node, index) => new PositionedNode(node,
            (index % columns + 0.5f) / columns, (index / columns + 0.5f) / rows)).ToArray();
        var edges = relationships.Take(300).Where(edge => ids.Contains(edge.From) && ids.Contains(edge.To)
            && edge.From != edge.To && !string.IsNullOrWhiteSpace(edge.Evidence)).ToArray();
        return new GraphScene(placed, edges, bounded.Length > MaxNodes);
    }

    public static double Contrast(uint first, uint second)
    {
        static double Luminance(uint rgb)
        {
            static double Channel(uint value)
            { var n = value / 255d; return n <= 0.04045 ? n / 12.92 : Math.Pow((n + 0.055) / 1.055, 2.4); }
            return 0.2126 * Channel((rgb >> 16) & 255) + 0.7152 * Channel((rgb >> 8) & 255)
                + 0.0722 * Channel(rgb & 255);
        }
        var a = Luminance(first); var b = Luminance(second);
        return (Math.Max(a, b) + 0.05) / (Math.Min(a, b) + 0.05);
    }
}
