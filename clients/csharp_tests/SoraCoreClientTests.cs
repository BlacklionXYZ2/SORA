using System;
using Newtonsoft.Json;
using Xunit;
using Sora.Embodiment.Network;

namespace Sora.Embodiment.Tests
{
    public class SoraCoreClientTests
    {
        private static string Command(int revision = 3, DateTime? created = null) =>
            JsonConvert.SerializeObject(new { type = "embodiment.command", command = new {
                command_id = "cmd", verb = "move_to", topology_revision = revision,
                created_at = created ?? DateTime.UtcNow, target_point = new { x = 40, y = 20 },
                speed_px_per_sec = 100 }});
        [Fact]
        public void HydrationDuplicatesAndStaleCommands()
        {
            using var client = new SoraCoreClient();
            int calls = 0;
            client.OnCommandReceived += _ => calls++;
            client.ProcessIncomingMessage(Command());
            Assert.Equal(0, calls);
            client.ProcessIncomingMessage("{\"type\":\"embodiment.snapshot\",\"projection\":{\"revision\":3}}");
            client.ProcessIncomingMessage(Command(2));
            client.ProcessIncomingMessage(Command(3, DateTime.UtcNow.AddMinutes(-1)));
            Assert.Equal(0, calls);
            client.ProcessIncomingMessage(Command());
            client.ProcessIncomingMessage(Command());
            Assert.Equal(1, calls);
        }
        [Fact]
        public void ActualResyncEnvelope()
        {
            using var client = new SoraCoreClient();
            bool resync = false;
            client.OnResyncRequired += () => resync = true;
            client.ProcessIncomingMessage("{\"type\":\"resync_required\",\"latest_sequence\":10}");
            Assert.True(resync);
            Assert.Equal(0, client.TopologyRevision);
        }
        [Fact]
        public void RemotePlaintextTokenTransportIsRejected() =>
            Assert.Throws<ArgumentException>(() => new SoraCoreClient("example.com", authToken: "secret"));

        [Fact]
        public void SemanticPresentationStatesActionsAndStylesAreValidated()
        {
            using var client = new SoraCoreClient();
            var accepted = new System.Collections.Generic.List<EmbodimentCommandDto>();
            client.OnCommandReceived += accepted.Add;
            client.ProcessIncomingMessage("{\"type\":\"embodiment.snapshot\",\"projection\":{\"revision\":3}}");

            string Envelope(object command) => JsonConvert.SerializeObject(new {
                type = "embodiment.command", command
            });
            client.ProcessIncomingMessage(Envelope(new {
                command_id = "thinking", verb = "set_state", state = "thinking",
                presentation_style = "focused", topology_revision = 3, created_at = DateTime.UtcNow
            }));
            client.ProcessIncomingMessage(Envelope(new {
                command_id = "derived", verb = "set_state", state = "moving",
                topology_revision = 3, created_at = DateTime.UtcNow
            }));
            client.ProcessIncomingMessage(Envelope(new {
                command_id = "waving", verb = "set_state", state = "waving",
                topology_revision = 3, created_at = DateTime.UtcNow
            }));
            client.ProcessIncomingMessage(Envelope(new {
                command_id = "point", verb = "presentation_phase", semantic_action_id = "action-1",
                semantic_action = "point", semantic_phase = "reach", presentation_style = "careful",
                topology_revision = 3, created_at = DateTime.UtcNow
            }));
            client.ProcessIncomingMessage(Envelope(new {
                command_id = "unknown-action", verb = "presentation_phase", semantic_action_id = "action-2",
                semantic_action = "delete_everything", semantic_phase = "contact",
                topology_revision = 3, created_at = DateTime.UtcNow
            }));
            client.ProcessIncomingMessage(Envelope(new {
                command_id = "bad-style", verb = "set_state", state = "thinking",
                presentation_style = "bad style", topology_revision = 3, created_at = DateTime.UtcNow
            }));

            Assert.Collection(accepted,
                state => { Assert.Equal("thinking", state.State); Assert.Equal("focused", state.PresentationStyle); },
                state => Assert.Equal("waving", state.State),
                action => { Assert.Equal("point", action.SemanticAction); Assert.Equal("reach", action.SemanticPhase); });
        }
    }
}
