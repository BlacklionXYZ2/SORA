using System;
using NUnit.Framework;
using Sora.Embodiment.Voice;
using UnityEngine;
using UnityEngine.TestTools;
using System.Collections;

public sealed class P14VoicePresentationTests
{
    [Test]
    public void NewWorkerStreamCanRestartItsSessionEpochAtZero()
    {
        var go = new GameObject("Voice worker restart");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("old", 9, "neutral"));
            controller.ResetTransport();
            Assert.IsTrue(controller.Begin("new", 0, "warm"));
            Assert.IsFalse(controller.ApplyFrame(new VoicePresentationFrame(
                "old", 9, 0, 0, 100, .8f, "neutral")));
            Assert.AreEqual(0, controller.MouthOpen);
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }

    [UnityTest]
    public IEnumerator TransportOrSynthesisGapCannotFreezeOpenMouth()
    {
        var go = new GameObject("Voice mouth watchdog");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("p", 0, "neutral"));
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "p", 0, 0, 0, 100, .8f, "neutral")));
            yield return new WaitForSecondsRealtime(.45f);
            Assert.AreEqual(0, controller.MouthOpen);
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "p", 0, 1, 100, 100, .4f, "neutral")));
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }
    [Test]
    public void FiveVowelSharesAreCarriedAndClearedWithPlayback()
    {
        var go = new GameObject("Five-vowel lip sync fixture");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("vowels", 1, "neutral"));
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "vowels", 1, 0, 0, 100, .6f, "neutral", new[] { 0f, .1f, .9f, 0f, 0f })));
            Assert.AreEqual(.9f, controller.Vowels[2]);
            Assert.Throws<ArgumentOutOfRangeException>(() => new VoicePresentationFrame(
                "vowels", 1, 1, 100, 100, .6f, "neutral", new[] { 0f, 0f, 2f, 0f, 0f }));
            Assert.AreEqual(0f, new VoicePresentationFrame(
                "vowels", 1, 1, 100, 100, .6f, "neutral").Vowels[0]);
            controller.ResetAll(VoicePresentationResetReason.Completed);
            Assert.AreEqual(0f, controller.Vowels[2]);
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }

    [Test]
    public void OrderedAudioClockDrivesBoundedMouthAndCoarseEmotion()
    {
        var go = new GameObject("P14 voice presentation fixture");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("playback-one", 3, "warm"));
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "playback-one", 3, 0, 0, 10, 0.2f, "warm")));
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "playback-one", 3, 1, 10, 10, 0.8f, "warm")));
            Assert.AreEqual(0.8f, controller.MouthOpen);
            Assert.AreEqual("warm", controller.Emotion);
            Assert.Throws<ArgumentOutOfRangeException>(() => new VoicePresentationFrame(
                "playback-one", 3, 2, 20, 10, 1.1f, "warm"));
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }

    [Test]
    public void ResetAndNewPlaybackRejectEveryStaleFrame()
    {
        var go = new GameObject("P14 stale frame fixture");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("old-playback", 4, "cheerful"));
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "old-playback", 4, 0, 0, 10, 0.9f, "cheerful")));
            Assert.IsTrue(controller.Reset("old-playback", 4,
                VoicePresentationResetReason.Interrupted));
            Assert.AreEqual(0, controller.MouthOpen);
            Assert.AreEqual("neutral", controller.Emotion);
            Assert.IsTrue(controller.Begin("new-playback", 5, "focused"));
            Assert.IsFalse(controller.ApplyFrame(new VoicePresentationFrame(
                "old-playback", 4, 1, 10, 10, 0.9f, "cheerful")));
            Assert.IsFalse(controller.Reset("old-playback", 4,
                VoicePresentationResetReason.Completed));
            Assert.AreEqual("new-playback", controller.ActivePlaybackId);
            Assert.AreEqual(0, controller.MouthOpen);
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }

    [TestCase(VoicePresentationResetReason.Paused)]
    [TestCase(VoicePresentationResetReason.Interrupted)]
    [TestCase(VoicePresentationResetReason.Disconnected)]
    public void PauseInterruptAndDisconnectResetMouth(VoicePresentationResetReason reason)
    {
        var go = new GameObject("P14 reset fixture");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("playback-reset", 7, "concerned"));
            Assert.IsTrue(controller.ApplyFrame(new VoicePresentationFrame(
                "playback-reset", 7, 0, 0, 20, 0.75f, "concerned")));
            controller.ResetAll(reason);
            Assert.IsNull(controller.ActivePlaybackId);
            Assert.AreEqual(0, controller.MouthOpen);
            Assert.AreEqual("neutral", controller.Emotion);
            Assert.AreEqual(reason, controller.LastResetReason);
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }

    [Test]
    public void InvalidSequenceAndClockCannotMoveMouth()
    {
        var go = new GameObject("P14 invalid clock fixture");
        try
        {
            var controller = go.AddComponent<AvatarVoicePresentationController>();
            Assert.IsTrue(controller.Begin("playback-clock", 2, "neutral"));
            Assert.IsFalse(controller.ApplyFrame(new VoicePresentationFrame(
                "playback-clock", 2, 1, 0, 10, 0.8f, "neutral")));
            Assert.IsFalse(controller.ApplyFrame(new VoicePresentationFrame(
                "playback-clock", 2, 0, 50, 10, 0.8f, "neutral")));
            Assert.AreEqual(0, controller.MouthOpen);
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
    }
}
