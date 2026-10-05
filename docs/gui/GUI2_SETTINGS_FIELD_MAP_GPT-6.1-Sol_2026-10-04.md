# GUI-2 canonical v9 Settings field map

Model name: **GPT-6.1 Sol**. Mapping checkpoint: **2026-10-04 07:21:29 +01:00**, Europe/London. Status: **implemented mapping / GUI-2 in progress**, not native acceptance or stage completion.

All 84 editable v9 preference leaves are mapped explicitly in `src/sora/runtime/app_settings.py`. Root version/revision/delegation epoch remain Core-owned bookkeeping, not user controls. Category and advanced-disclosure metadata are projection-only: they do not change persisted AppSettings v9, authorization, defaults, validation or canonical effect tiers. The shared editor retains all controls even when their category/disclosure is hidden. Older canonical v9 Core responses use `SettingsCategories` fallback; unknown keys stay in Advanced rather than disappear. Current Python tests enforce exact coverage, uniqueness, valid categories and disclosure keys.

The ten-category rail includes Appearance (links to the real UI-only store), Memory and Automation (explicit unavailable descriptions until their supported services/settings exist). There are no invented memory/scheduler fields, fake VRAM/capability data, arbitrary raw launch flags, or new per-file permission prompts.

| Canonical field | Category | Disclosure | Effect | Control kind |
|---|---|---|---|---|
| `local_companion.desktop_observe` | Vision | Visible | live | bool |
| `local_companion.desktop_capture` | Vision | Visible | live | bool |
| `local_companion.file_read` | Tools | Visible | live | bool |
| `local_companion.desktop_interact` | Tools | Visible | live | bool |
| `local_companion.avatar_control` | Tools | Visible | live | bool |
| `local_companion.agent_delegation` | Tools | Visible | live | bool |
| `local_companion.direct_file_write` | Tools | Visible | live | bool |
| `local_companion.voice` | Audio | Visible | live | bool |
| `perception.mode` | Vision | Visible | live | enum |
| `perception.paused` | Vision | Visible | live | bool |
| `perception.window_context` | Vision | Visible | live | bool |
| `perception.desktop_context` | Vision | Visible | live | bool |
| `perception.interval_seconds` | Vision | Visible | live | float |
| `perception.context_max_age_seconds` | Vision | Visible | live | float |
| `dialogue.backend` | General | Visible | next_boot | enum |
| `dialogue.timeout_seconds` | General | Advanced checkbox | live | float |
| `dialogue.context_max_chars` | General | Advanced checkbox | live | int |
| `llama.executable` | Advanced | Visible | next_boot | path-exe |
| `llama.model_path` | Models | Visible | model_reload | path-gguf |
| `llama.mmproj_path` | Models | Visible | model_reload | path-gguf |
| `llama.port` | Advanced | Visible | next_boot | int |
| `llama.context_size` | Models | Visible | model_reload | int |
| `llama.gpu_layers` | Models | Visible | model_reload | gpu |
| `llama.startup_timeout` | Advanced | Visible | next_boot | float |
| `llama.flash_attn` | Models | Visible | model_reload | enum |
| `llama.cache_type_k` | Models | Visible | model_reload | enum |
| `llama.cache_type_v` | Models | Visible | model_reload | enum |
| `llama.batch_size` | Performance | Visible | model_reload | int |
| `llama.ubatch_size` | Performance | Visible | model_reload | int |
| `llama.split_mode` | Performance | Visible | model_reload | enum |
| `llama.tensor_split` | Performance | Visible | model_reload | string |
| `llama.main_gpu` | Performance | Visible | model_reload | int |
| `llama.cpu_moe` | Performance | Visible | model_reload | bool |
| `llama.n_cpu_moe` | Performance | Visible | model_reload | int |
| `llama.load_mode` | Performance | Visible | model_reload | enum |
| `llama.swa_full` | Performance | Visible | model_reload | bool |
| `llama.speculative.type` | Models | Visible | model_reload | enum |
| `llama.speculative.draft_model_path` | Models | Visible | model_reload | path-gguf |
| `llama.speculative.draft_gpu_layers` | Models | Advanced checkbox | model_reload | gpu |
| `llama.speculative.draft_cache_type_k` | Models | Advanced checkbox | model_reload | enum |
| `llama.speculative.draft_cache_type_v` | Models | Advanced checkbox | model_reload | enum |
| `llama.speculative.draft_tokens_min` | Models | Advanced checkbox | model_reload | int |
| `llama.speculative.draft_tokens_max` | Models | Advanced checkbox | model_reload | int |
| `external.model` | Models | Visible | next_boot | string |
| `external.base_url` | Models | Visible | next_boot | string |
| `external.model_folder` | Models | Advanced checkbox | next_boot | path-dir |
| `runtime.worker_count` | Performance | Visible | next_boot | int |
| `runtime.task_timeout_seconds` | Tools | Visible | live | float |
| `voice.python_executable` | Audio | Advanced checkbox | live | path-exe |
| `voice.stt_model_path` | Audio | Advanced checkbox | live | path-dir |
| `voice.tts_model_path` | Audio | Advanced checkbox | live | path-file |
| `voice.voices_path` | Audio | Advanced checkbox | live | path-file |
| `voice.input_device` | Audio | Visible | live | string |
| `voice.output_device` | Audio | Visible | live | string |
| `voice.voice_id` | Audio | Visible | live | string |
| `voice.recording_limit_seconds` | Audio | Visible | live | int |
| `voice.speech_speed` | Audio | Visible | live | float |
| `agents.codex.enabled` | Models | Visible | live | bool |
| `agents.codex.purpose` | Models | Visible | live | string |
| `agents.codex.preferred_model` | Models | Visible | live | agent-model |
| `agents.codex.preferred_effort` | Models | Visible | live | enum |
| `agents.codex.model_purpose` | Models | Visible | live | string |
| `agents.codex.model_choices` | Models | Visible | live | agent-model-purposes |
| `agents.codex.project_root` | Tools | Visible | live | path-dir |
| `agents.codex.workspace_mode` | Tools | Visible | live | enum |
| `agents.codex.base_ref` | Tools | Visible | live | string |
| `agents.hermes.enabled` | Models | Visible | live | bool |
| `agents.hermes.purpose` | Models | Visible | live | string |
| `agents.hermes.preferred_model` | Models | Visible | live | agent-model |
| `agents.hermes.preferred_effort` | Models | Visible | live | enum |
| `agents.hermes.model_purpose` | Models | Visible | live | string |
| `agents.hermes.model_choices` | Models | Visible | live | agent-model-purposes |
| `agents.hermes.project_root` | Tools | Visible | live | path-dir |
| `agents.hermes.workspace_mode` | Tools | Visible | live | enum |
| `agents.hermes.base_ref` | Tools | Visible | live | string |
| `agents.antigravity.enabled` | Models | Visible | live | bool |
| `agents.antigravity.purpose` | Models | Visible | live | string |
| `agents.antigravity.preferred_model` | Models | Visible | live | agent-model |
| `agents.antigravity.preferred_effort` | Models | Visible | live | enum |
| `agents.antigravity.model_purpose` | Models | Visible | live | string |
| `agents.antigravity.model_choices` | Models | Visible | live | agent-model-purposes |
| `agents.antigravity.project_root` | Tools | Visible | live | path-dir |
| `agents.antigravity.workspace_mode` | Tools | Visible | live | enum |
| `agents.antigravity.base_ref` | Tools | Visible | live | string |

`live` means application on Save (voice changes stop active audio; disabled agents revoke local runs), `model_reload` means saved first and applied only by explicit Reload model, and `next_boot` means the next controlled Core start. Agent/project preferences apply to new admissions; editing metadata does not establish provider entitlement.

