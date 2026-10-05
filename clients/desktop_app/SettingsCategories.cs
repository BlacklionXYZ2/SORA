using System.Text.Json;

namespace Sora.DesktopApp;

public static class SettingsCategories
{
    // Fallback for canonical v9 Cores started before category metadata was added.
    // Unknown future keys remain inspectable/editable in Advanced, never dropped.
    public static string ForKey(string key) => key switch {
        "dialogue.backend" or "dialogue.timeout_seconds" or "dialogue.context_max_chars" => "General",
        "local_companion.voice" => "Audio",
        "local_companion.desktop_observe" or "local_companion.desktop_capture" => "Vision",
        "llama.executable" or "llama.port" or "llama.startup_timeout" => "Advanced",
        "llama.batch_size" or "llama.ubatch_size" or "llama.split_mode" or "llama.tensor_split"
            or "llama.main_gpu" or "llama.cpu_moe" or "llama.n_cpu_moe" or "llama.load_mode"
            or "llama.swa_full" or "runtime.worker_count" => "Performance",
        "runtime.task_timeout_seconds" => "Tools",
        _ when key.StartsWith("agents.") => key.Split('.').Last() is "project_root" or "workspace_mode" or "base_ref" ? "Tools" : "Models",
        _ when key.StartsWith("llama.") || key.StartsWith("external.") => "Models",
        _ when key.StartsWith("voice.") => "Audio",
        _ when key.StartsWith("perception.") => "Vision",
        _ when key.StartsWith("local_companion.") => "Tools",
        _ => "Advanced"
    };
    public static string Category(JsonElement field) => field.TryGetProperty("category", out var category)
        && category.ValueKind == JsonValueKind.String ? category.GetString()! : ForKey(field.GetProperty("key").GetString()!);
    public static bool Advanced(JsonElement field)
    {
        if (field.TryGetProperty("advanced", out var advanced)) return advanced.ValueKind == JsonValueKind.True;
        return field.GetProperty("key").GetString() is "dialogue.timeout_seconds" or "dialogue.context_max_chars"
            or "external.model_folder" or "voice.python_executable" or "voice.stt_model_path" or "voice.tts_model_path"
            or "voice.voices_path" or "llama.speculative.draft_gpu_layers" or "llama.speculative.draft_cache_type_k"
            or "llama.speculative.draft_cache_type_v" or "llama.speculative.draft_tokens_min" or "llama.speculative.draft_tokens_max";
    }
}
