using System;
using System.Collections.Generic;

namespace Sora.Embodiment.Network
{
    /// <summary>Bounded edge-event queue with local cooldown and terminal deduplication.</summary>
    public sealed class EmbodimentFeedbackBuffer
    {
        private const int MaximumPending = 64;
        private static readonly HashSet<string> Kinds = new HashSet<string>(StringComparer.Ordinal)
        {
            "grabbed", "released", "fell", "landed", "support_removed",
            "clicked", "poked", "completed", "failed"
        };
        private readonly Queue<EmbodimentFeedbackDto> _pending =
            new Queue<EmbodimentFeedbackDto>();
        private readonly Dictionary<string, double> _last =
            new Dictionary<string, double>(StringComparer.Ordinal);
        private readonly HashSet<string> _terminals = new HashSet<string>(StringComparer.Ordinal);
        private readonly Func<double> _clock;

        public int Count => _pending.Count;

        public EmbodimentFeedbackBuffer(Func<double> clock)
        {
            _clock = clock ?? throw new ArgumentNullException(nameof(clock));
        }

        public bool TryEnqueue(string kind, TargetPointDto position, int topologyRevision,
            string? subjectId = null, string? correlationId = null, string? detail = null,
            float? magnitude = null)
        {
            if (!Kinds.Contains(kind) || position == null || topologyRevision < 1 ||
                _pending.Count >= MaximumPending ||
                (kind == "support_removed" && string.IsNullOrWhiteSpace(subjectId)) ||
                ((kind == "completed" || kind == "failed") &&
                    string.IsNullOrWhiteSpace(correlationId))) return false;
            if ((kind == "completed" || kind == "failed") && !_terminals.Add(correlationId!))
                return false;
            double now = _clock();
            string key = kind + ":" + (subjectId ?? correlationId ?? "");
            double cooldown = kind == "clicked" || kind == "poked" ? 0.5 : 0.2;
            if (_last.TryGetValue(key, out var previous) && now - previous < cooldown)
                return false;
            _last[key] = now;
            _pending.Enqueue(new EmbodimentFeedbackDto
            {
                EventId = "physics:" + Guid.NewGuid().ToString("N"),
                Kind = kind,
                OccurredAt = DateTime.UtcNow,
                TopologyRevision = topologyRevision,
                Position = position,
                SubjectId = subjectId,
                CorrelationId = correlationId,
                Detail = detail,
                Magnitude = magnitude,
            });
            return true;
        }

        public bool TryDequeue(out EmbodimentFeedbackDto? value)
        {
            if (_pending.Count == 0)
            {
                value = null;
                return false;
            }
            value = _pending.Dequeue();
            return true;
        }
    }
}
