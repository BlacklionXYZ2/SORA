using System;
using UniGLTF.SpringBoneJobs.Blittables;
using UniVRM10;
using UnityEngine;

namespace Sora.Embodiment.Avatar
{
    public readonly struct StableSpringBoneSettings
    {
        public float Stiffness { get; }
        public float GravityPower { get; }
        public Vector3 GravityDirection { get; }
        public float Drag { get; }
        public float Radius { get; }

        public StableSpringBoneSettings(float stiffness, float gravityPower,
            Vector3 gravityDirection, float drag, float radius)
        {
            Stiffness = stiffness;
            GravityPower = gravityPower;
            GravityDirection = gravityDirection;
            Drag = drag;
            Radius = radius;
        }
    }

    /// <summary>Applies finite runtime-only bounds to imported VRM spring joints.</summary>
    public sealed class AvatarSecondaryMotionTuner : MonoBehaviour
    {
        private Vrm10Instance? _instance;
        public int TunedJointCount { get; private set; }

        public int Configure(Vrm10Instance instance)
        {
            _instance = instance ?? throw new ArgumentNullException(nameof(instance));
            TunedJointCount = 0;
            foreach (var joint in instance.GetComponentsInChildren<VRM10SpringBoneJoint>(true))
            {
                var settings = Stabilize(joint.m_stiffnessForce, joint.m_gravityPower,
                    joint.m_gravityDir, joint.m_dragForce, joint.m_jointRadius);
                var mutable = new BlittableJointMutable(
                    stiffnessForce: settings.Stiffness,
                    gravityPower: settings.GravityPower,
                    gravityDir: settings.GravityDirection,
                    dragForce: settings.Drag,
                    radius: settings.Radius,
                    angleLimitType: (float)joint.m_anglelimitType,
                    angleLimit1: Mathf.Clamp(joint.m_pitch, 0, Mathf.PI),
                    angleLimit2: Mathf.Clamp(joint.m_yaw, 0, Mathf.PI / 2),
                    angleLimitOffset: IsFinite(joint.m_limitSpaceOffset) ?
                        joint.m_limitSpaceOffset : Quaternion.identity);
                instance.Runtime.SpringBone.SetJointLevel(joint.transform, mutable);
                TunedJointCount++;
            }
            Debug.Log("Secondary motion tuned: " + TunedJointCount + " spring joints");
            return TunedJointCount;
        }

        public void ResetSimulation()
        {
            if (_instance != null) _instance.Runtime.SpringBone.RestoreInitialTransform();
        }

        public static StableSpringBoneSettings Stabilize(float stiffness, float gravityPower,
            Vector3 gravityDirection, float drag, float radius)
        {
            stiffness = IsFinite(stiffness) ? Mathf.Clamp(stiffness, 0, 4f) : 1f;
            gravityPower = IsFinite(gravityPower) ? Mathf.Clamp(gravityPower, 0, 1.5f) : 0;
            drag = IsFinite(drag) ? Mathf.Clamp(drag, 0.35f, 0.9f) : 0.5f;
            radius = IsFinite(radius) ? Mathf.Clamp(radius, 0, 0.2f) : 0.02f;
            if (!IsFinite(gravityDirection) || gravityDirection.sqrMagnitude < 0.000001f)
                gravityDirection = Vector3.down;
            else
                gravityDirection.Normalize();
            return new StableSpringBoneSettings(stiffness, gravityPower, gravityDirection,
                drag, radius);
        }

        private static bool IsFinite(Vector3 value) => IsFinite(value.x) &&
            IsFinite(value.y) && IsFinite(value.z);
        private static bool IsFinite(Quaternion value) => IsFinite(value.x) &&
            IsFinite(value.y) && IsFinite(value.z) && IsFinite(value.w) &&
            value.x * value.x + value.y * value.y + value.z * value.z +
                value.w * value.w > 0.000001f;
        private static bool IsFinite(float value) => !float.IsNaN(value) &&
            !float.IsInfinity(value);
    }
}
