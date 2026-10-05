using Newtonsoft.Json;
using Sora.Embodiment.Network;

public sealed class VoiceTransportTests
{
    private static string Wire(VoiceSampleDto sample) => JsonConvert.SerializeObject(
        new { type = "embodiment.voice", sample });

    [Fact]
    public void VoiceIsSeparateOrderedTransientMetadata()
    {
        using var client = new SoraCoreClient();
        var accepted = new List<VoiceSampleDto>();
        int actions = 0;
        client.OnCommandReceived += _ => actions++;
        client.OnVoiceSampleReceived += accepted.Add;
        var begin = new VoiceSampleDto { Op = "begin", StreamId = "worker-one", Serial = 1,
            PlaybackId = "playback-one", OutputEpoch = 0, EmittedAt = DateTime.UtcNow };
        client.ProcessIncomingMessage(Wire(begin));
        client.ProcessIncomingMessage(Wire(begin));
        client.ProcessIncomingMessage(Wire(new VoiceSampleDto { Op = "frame", StreamId = "worker-one",
            Serial = 2, PlaybackId = "playback-one", OutputEpoch = 0, Sequence = 0,
            DurationMs = 100, MouthOpen = .4f, EmittedAt = DateTime.UtcNow }));
        Assert.Equal(2, accepted.Count);
        Assert.Equal(.4f, accepted[1].MouthOpen);
        Assert.Equal(0, actions);
    }

    [Theory]
    [InlineData(2f, 0)]
    [InlineData(.4f, 5)]
    public void InvalidOrStaleFrameBecomesReset(float mouth, int secondsOld)
    {
        using var client = new SoraCoreClient();
        VoiceSampleDto? accepted = null;
        client.OnVoiceSampleReceived += sample => accepted = sample;
        client.ProcessIncomingMessage(Wire(new VoiceSampleDto { Op = "frame", StreamId = "worker-one",
            Serial = 1, PlaybackId = "p", OutputEpoch = 0, DurationMs = 100,
            MouthOpen = mouth, EmittedAt = DateTime.UtcNow.AddSeconds(-secondsOld) }));
        Assert.NotNull(accepted);
        Assert.Equal("reset", accepted!.Op);
        Assert.Null(accepted.PlaybackId);
    }
}
