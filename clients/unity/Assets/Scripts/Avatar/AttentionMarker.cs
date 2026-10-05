using System;
using Sora.Embodiment.Coordinates;
using Sora.Embodiment.Network;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    /// <summary>Presentation only. Never injects input, acquires a collider, or authorizes an effect.</summary>
    public sealed class AttentionMarker : MonoBehaviour
    {
        private LineRenderer _line = null!;
        private Material _material = null!;
        private float _expires;
        private readonly CoordinateTransformer _coordinates = new CoordinateTransformer();
        public string? TargetId { get; private set; }
        public TargetPointDto? Point { get; private set; }
        public string? LastPhase { get; private set; }
        public event Action<string, string>? OnSemanticPhase;

        private void Awake()
        {
            _line = gameObject.AddComponent<LineRenderer>();
            _material = new Material(Shader.Find("Sprites/Default"));
            _line.sharedMaterial = _material;
            _line.useWorldSpace = true;
            _line.loop = true;
            _line.startWidth = _line.endWidth = 3f / 500f;
            _line.startColor = _line.endColor = Color.cyan;
            _line.enabled = false;
        }

        public void Show(EmbodimentCommandDto command, DisplayTopology topology)
        {
            var point = command.TargetPoint!;
            var rect = command.TargetRect?.ToScreenRect() ?? new ScreenRect(point.X - 12, point.Y - 12, 25, 25);
            var vertices = new[] { (rect.X, rect.Y), (rect.Right - 1, rect.Y),
                (rect.Right - 1, rect.Bottom - 1), (rect.X, rect.Bottom - 1) };
            _line.positionCount = vertices.Length;
            for (int i = 0; i < vertices.Length; i++)
            {
                var world = _coordinates.GlobalToWorld(vertices[i].Item1, vertices[i].Item2, topology);
                _line.SetPosition(i, new Vector3(world.X, world.Y, -1));
            }
            TargetId = command.TargetId;
            Point = new TargetPointDto(point.X, point.Y);
            _expires = Time.unscaledTime + command.MarkerDurationSeconds;
            _line.enabled = true;
        }

        public void ConsumePhase(EmbodimentCommandDto command)
        {
            if (string.IsNullOrWhiteSpace(command.SemanticActionId) || string.IsNullOrWhiteSpace(command.SemanticPhase)) return;
            LastPhase = command.SemanticPhase;
            OnSemanticPhase?.Invoke(command.SemanticActionId!, command.SemanticPhase!);
            // This hook describes another coordinator's phase. It proves no contact or OS effect.
        }

        public void Hide() { _line.enabled = false; TargetId = null; Point = null; LastPhase = null; }
        private void Update() { if (_line.enabled && Time.unscaledTime >= _expires) Hide(); }
        private void OnDestroy() { if (_material != null) Destroy(_material); }
    }
}
