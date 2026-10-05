using System;
using System.IO;
using Sora.Embodiment;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

public static class SoraBuild
{
    public const string ScenePath = "Assets/Scenes/SoraOverlay.unity";

    [MenuItem("SORA/Prepare overlay project")]
    public static void Prepare()
    {
        PlayerSettings.companyName = "SORA";
        PlayerSettings.productName = "SORA";
        PlayerSettings.runInBackground = true;
        PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
        PlayerSettings.defaultScreenWidth = 1280;
        PlayerSettings.defaultScreenHeight = 720;
        PlayerSettings.resizableWindow = true;
        PlayerSettings.allowFullscreenSwitch = false;
        PlayerSettings.usePlayerLog = true;
        PlayerSettings.colorSpace = ColorSpace.Gamma;
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);
        PlayerSettings.SetApiCompatibilityLevel(UnityEditor.Build.NamedBuildTarget.Standalone, ApiCompatibilityLevel.NET_Standard);
        PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.StandaloneWindows64, false);
        PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneWindows64, new[] { GraphicsDeviceType.Direct3D11 });
        PlayerSettings.useFlipModelSwapchain = false; // DWM glass requires the compatible blit presentation path.
        PlayerSettings.enableFrameTimingStats = true;
        // Runtime-loaded VRMs do not create serialized scene material references.
        // Keep their built-in pipeline shaders in player builds explicitly.
        var graphics = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/GraphicsSettings.asset")[0]);
        var shaders = graphics.FindProperty("m_AlwaysIncludedShaders");
        foreach (var name in new[] { "VRM10/MToon10", "UniGLTF/UniUnlit", "Standard", "Sprites/Default" })
        {
            var shader = Shader.Find(name);
            if (shader == null) throw new InvalidOperationException("Required runtime shader missing: " + name);
            bool present = false;
            for (int i = 0; i < shaders.arraySize; i++)
                if (shaders.GetArrayElementAtIndex(i).objectReferenceValue == shader) present = true;
            if (!present) { shaders.InsertArrayElementAtIndex(shaders.arraySize); shaders.GetArrayElementAtIndex(shaders.arraySize - 1).objectReferenceValue = shader; }
        }
        graphics.ApplyModifiedPropertiesWithoutUndo();
        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        new GameObject("SORA Bootstrap").AddComponent<SoraBootstrap>();
        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        AssetDatabase.SaveAssets();
    }

    [MenuItem("SORA/Build Windows overlay")]
    public static void Windows()
    {
        Prepare();
        string output = Environment.GetEnvironmentVariable("SORA_UNITY_BUILD_PATH") ?? "Builds/Windows/SORA.exe";
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        var result = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
            scenes = new[] { ScenePath }, locationPathName = output,
            target = BuildTarget.StandaloneWindows64, options = BuildOptions.Development });
        if (result.summary.result != BuildResult.Succeeded)
            throw new InvalidOperationException("SORA Windows build failed: " + result.summary.result);
    }
}
