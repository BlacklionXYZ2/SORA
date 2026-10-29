# Motion core M0 runtime spike: evidence

Observed by **Opus 5.5**, 2026-10-12, on the owner's PC (Intel i5-14600K, AMD RX 9070 XT, Unity
6000.6.0f1). Code in `~/Desktop/motion-lab` (uncommitted): `scripts/spike_export.py`,
`unity-spike/` (a scratch Unity project, never SORA's), and the write-up
`docs/RUNTIME_SPIKE.md`. Plan: [MOTION-CORE-ROADMAP_2026-10-11](../plans/MOTION-CORE-ROADMAP_2026-10-11.md),
M0's runtime spike and decision 4.

**Evidence kind:**
- **component:** Python export and parity, and Unity editor parity and timing;
- **native:** a built Unity player driving Alice at 60 Hz.

The model weights are random (seeded), so motion quality isn't evidence here.

## Findings

1. **Unity's Sentis (Inference Engine 2.6.1) has no ONNX `GRU` operator.** The package's
   supported-operators page lists it as unsupported; `LSTM` is supported.
   - The export now writes the GRU as its cell equations, with the trained `nn.GRU`'s weights.
   - The graph's operators are Add, Concat, Gather, Gelu, Gemm, MatMul, Mul, Sigmoid, Split,
     Sub, Tanh and Unsqueeze, all supported by Sentis.
   - onnxruntime matches PyTorch to 5.4e-7 over 120 ticks, at all six sizes.
   - New tests check that the graph has no `GRU` node, for one and two layers.
2. **Parity in Unity:** Sentis CPU, Sentis GPU and a hand-written C# GRU all match PyTorch's
   reference run to within 2.5e-7, at every size (editor, 120 ticks, hidden state fed back).
3. **Built player, driving Alice at 60 Hz.** The player used SORA's own player settings: Mono,
   Direct3D 11 and a Development build. Each figure is the mean of 600 frames, with the 99th
   percentile in brackets:

   | Size | Parameters | Sentis CPU | Sentis GPU | C# GRU |
   |---|---|---|---|---|
   | 128 × 1 | 0.24M | 0.25 (0.44) ms | 0.71 (0.96) ms | 0.88 (0.95) ms |
   | 256 × 1 | 0.53M | 0.29 (0.54) ms | 0.78 (1.02) ms | 1.87 (1.95) ms |
   | 512 × 1 | 1.40M | 0.40 (0.71) ms | 0.91 (1.19) ms | 4.88 (5.03) ms |
   | 128 × 2 | 0.34M | 0.30 (0.48) ms | 0.81 (1.05) ms | 1.22 (1.33) ms |
   | 256 × 2 | 0.93M | 0.40 (0.81) ms | 0.93 (1.20) ms | 3.24 (3.37) ms |
   | 512 × 2 | 2.98M | 0.68 (1.13) ms | 1.14 (1.39) ms | 10.44 (11.00) ms |

   - A tick covers the motion state from her realised pose, the model, 6D decoding, folding
     `upperChest` into `chest`, and writing her control-rig bones.
   - Every run held 16.70 ms frames, and all outputs were finite.
   - Applying the pose costs about 17 µs.
   - Screenshots show Alice rendered with her joints driven by the model.

## Decisions recorded

- **Runtime:** Sentis on the CPU.
  - The GPU loses at this size, because of the upload and readback each tick.
  - The plain C# GRU is too slow under Mono.
  - ONNX Runtime wasn't needed.
- **Budget (decision 4):** a tick may use a tenth of a 60 Hz frame, 1.67 ms at p99. All six
  sweep sizes fit, so **runtime doesn't constrain M1's model size**; data does. The owner can
  change this budget.

## Not run

- an IL2CPP or non-Development build;
- inference alongside SORA's own load (voice, the local model, capture). That belongs to M8.

M0's gate item, a second agent's line-by-line review of the skeleton table, is still open.
