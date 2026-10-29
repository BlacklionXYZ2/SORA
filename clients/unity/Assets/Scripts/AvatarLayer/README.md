# Avatar layer (from motion-lab)

Copies of motion-lab's avatar layer (`~/Desktop/motion-lab/unity-env/Assets/AvatarLayer`, roadmap
MA): the canonical skeleton, fitting, the physics body, falling, desktop surfaces and the stand-in
motion. **motion-lab's files are the source of truth.** Don't edit these; change motion-lab's and
run its `scripts/sync-to-sora.ps1`. A test fails if they drift. SORA uses them through
`Avatar/AvatarPhysicsBody.cs`.
