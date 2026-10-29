using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Xunit;
using Sora.Embodiment.Network;

namespace Sora.Embodiment.Tests
{
    /// <summary>Her motion model's stream as the player receives it (2026-10-27).</summary>
    public class MotionStreamTransportTests
    {
        private static object Frame(float w = 1f) => new
        {
            root = new[] { 0f, 0.9f, 0f },
            rot = Enumerable.Repeat(new[] { 0f, 0f, 0f, w }, 22).ToArray(),
            contacts = new[] { true, true, false, false },
        };

        private static string Motion(object body) =>
            JsonConvert.SerializeObject(new Dictionary<string, object> { ["type"] = "embodiment.motion" }
                .Concat(JsonConvert.DeserializeObject<Dictionary<string, object>>(JsonConvert.SerializeObject(body))!)
                .ToDictionary(p => p.Key, p => p.Value));

        private static List<MotionMessageDto> Receive(params string[] messages)
        {
            using var client = new SoraCoreClient();
            var received = new List<MotionMessageDto>();
            client.OnMotionReceived += received.Add;
            foreach (var message in messages) client.ProcessIncomingMessage(message);
            return received;
        }

        [Fact]
        public void SourceRecordSeedRequestAndChunksArrive()
        {
            var received = Receive(
                Motion(new { op = "source", source = "ardy" }),
                Motion(new { op = "record", seconds = 3.0 }),
                Motion(new { op = "seed_request" }),
                Motion(new { op = "chunk", chunk = new { seq = 0, t0 = 0.0, fps = 60, prompt = "walk|-|-",
                    frames = Enumerable.Repeat(Frame(), 24).ToArray() } }));
            Assert.Equal(new[] { "source", "record", "seed_request", "chunk" }, received.Select(m => m.Op));
            Assert.Equal("ardy", received[0].Source);
            Assert.Equal(24, received[3].Chunk!.Frames.Count);
            Assert.Equal(22, received[3].Chunk!.Frames[0].Rot.Length);
        }

        [Fact]
        public void MalformedMotionIsDroppedNotFatal()
        {
            var bad = Receive(
                Motion(new { op = "source", source = "teleport" }),
                Motion(new { op = "record", seconds = 60.0 }),
                Motion(new { op = "dance" }),
                // Not a unit quaternion, and too many frames.
                Motion(new { op = "chunk", chunk = new { seq = 0, t0 = 0.0, fps = 60, frames = new[] { Frame(2f) } } }),
                Motion(new { op = "chunk", chunk = new { seq = 0, t0 = 0.0, fps = 60,
                    frames = Enumerable.Repeat(Frame(), 65).ToArray() } }),
                Motion(new { op = "chunk", chunk = new { seq = 0, t0 = 0.0, fps = 30, frames = new[] { Frame() } } }));
            Assert.Empty(bad);
            // The connection keeps working afterwards: a valid message still arrives.
            Assert.Single(Receive(Motion(new { op = "dance" }), Motion(new { op = "seed_request" })));
        }
    }
}
