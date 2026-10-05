using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using Xunit;
using Sora.Embodiment.Coordinates;

namespace Sora.Embodiment.Tests
{
    public class CoordinateFixtureTests
    {
        [Fact]
        public void MixedDpiSeamIsContinuousAndInverseNeedsNoMonitorHint()
        {
            var topology = new DisplayTopology(new ScreenRect(0, 0, 3840, 1080), new[] {
                new MonitorDescriptor("a", true, new ScreenRect(0, 0, 1920, 1080)),
                new MonitorDescriptor("b", false, new ScreenRect(1920, 0, 1920, 1080), 1.5f) });
            var transform = new CoordinateTransformer();
            var left = transform.GlobalToWorld(1919, 400, topology);
            var right = transform.GlobalToWorld(1920, 400, topology);
            Assert.InRange(Math.Abs(right.X - left.X - 0.002f), 0, 0.000001f);
            Assert.Equal(left.Y, right.Y);
            for (int x = -200; x < 4100; x += 31)
            {
                var world = transform.GlobalToWorld(x, 500, topology);
                var actual = transform.WorldToGlobal(world, topology);
                Assert.InRange(Math.Abs(actual.GlobalX - x), 0, 1);
                Assert.Equal(500, actual.GlobalY);
                Assert.InRange(Math.Abs(world.X - x / 500f), 0, 0.000001f);
            }
        }

        private static JsonDocument LoadFixturesDocument()
        {
            // Search upward for contracts/fixtures/coordinate_fixtures.json
            string current = Directory.GetCurrentDirectory();
            while (!string.IsNullOrEmpty(current))
            {
                string candidate = Path.Combine(current, "contracts", "fixtures", "coordinate_fixtures.json");
                if (File.Exists(candidate))
                {
                    return JsonDocument.Parse(File.ReadAllText(candidate));
                }
                current = Directory.GetParent(current)?.FullName ?? "";
            }
            throw new FileNotFoundException("Unable to locate coordinate_fixtures.json");
        }

        public static IEnumerable<object[]> GetFixtureData()
        {
            using var doc = LoadFixturesDocument();
            var fixtures = doc.RootElement.GetProperty("fixtures");
            var result = new List<object[]>();

            foreach (var fixture in fixtures.EnumerateArray())
            {
                string fixtureId = fixture.GetProperty("fixture_id").GetString()!;
                result.Add(new object[] { fixtureId, fixture.Clone() });
            }

            return result;
        }

        [Theory]
        [MemberData(nameof(GetFixtureData))]
        public void Test_Coordinate_Fixtures_Against_CSharp_Transformer(string fixtureId, JsonElement fixture)
        {
            var vdElem = fixture.GetProperty("virtual_desktop");
            var vdRect = new ScreenRect(
                vdElem.GetProperty("x").GetInt32(),
                vdElem.GetProperty("y").GetInt32(),
                vdElem.GetProperty("width").GetInt32(),
                vdElem.GetProperty("height").GetInt32()
            );

            var monitors = new List<MonitorDescriptor>();
            foreach (var mElem in fixture.GetProperty("monitors").EnumerateArray())
            {
                var rectElem = mElem.GetProperty("rect");
                var mRect = new ScreenRect(
                    rectElem.GetProperty("x").GetInt32(),
                    rectElem.GetProperty("y").GetInt32(),
                    rectElem.GetProperty("width").GetInt32(),
                    rectElem.GetProperty("height").GetInt32()
                );
                monitors.Add(new MonitorDescriptor(
                    mElem.GetProperty("id").GetString()!,
                    mElem.GetProperty("primary").GetBoolean(),
                    mRect,
                    (float)mElem.GetProperty("dpi_scale").GetDouble(),
                    mElem.GetProperty("orientation").GetString()!
                ));
            }

            var topology = new DisplayTopology(vdRect, monitors, 1);
            var transformer = new CoordinateTransformer(500.0f);
            var manager = new DisplayTopologyManager(topology);

            foreach (var ptElem in fixture.GetProperty("test_points").EnumerateArray())
            {
                int gx = ptElem.GetProperty("global_px")[0].GetInt32();
                int gy = ptElem.GetProperty("global_px")[1].GetInt32();
                bool isGap = ptElem.GetProperty("is_in_gap").GetBoolean();

                var localRes = transformer.GlobalToMonitorLocal(gx, gy, topology);

                if (isGap)
                {
                    Assert.Null(localRes);

                    if (ptElem.TryGetProperty("expected_clamped_px", out var clampedElem))
                    {
                        int expectedClampedX = clampedElem[0].GetInt32();
                        int expectedClampedY = clampedElem[1].GetInt32();
                        var (clampedX, clampedY) = manager.ClampToNearestDisplay(gx, gy);
                        Assert.Equal((expectedClampedX, expectedClampedY), (clampedX, clampedY));
                    }
                }
                else
                {
                    Assert.NotNull(localRes);
                    var (monitor, lx, ly) = localRes.Value;
                    string expectedMonId = ptElem.GetProperty("expected_monitor_id").GetString()!;
                    int expectedLx = ptElem.GetProperty("expected_monitor_local_px")[0].GetInt32();
                    int expectedLy = ptElem.GetProperty("expected_monitor_local_px")[1].GetInt32();

                    Assert.Equal(expectedMonId, monitor.Id);
                    Assert.Equal((expectedLx, expectedLy), (lx, ly));

                    // Verify forward and inverse transform round-trip <= 1 physical pixel
                    var worldPt = transformer.GlobalToWorld(gx, gy, topology);
                    var (rtX, rtY) = transformer.WorldToGlobal(worldPt, topology, targetMonitorId: monitor.Id);

                    int errX = Math.Abs(rtX - gx);
                    int errY = Math.Abs(rtY - gy);

                    Assert.True(errX <= 1, $"X round-trip error > 1px in {fixtureId}: orig={gx}, got={rtX}");
                    Assert.True(errY <= 1, $"Y round-trip error > 1px in {fixtureId}: orig={gy}, got={rtY}");
                }
            }
        }
    }
}
