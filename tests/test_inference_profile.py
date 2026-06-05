from dragonclaw.inference_profile import (
    DEFAULT_REMOTE_MODEL,
    InferenceMode,
    inference_profile_path,
    load_inference_profile,
    save_inference_profile,
    set_local_mode,
    set_remote_byok_mode,
    should_use_remote_completion,
)


def test_default_remote_model_is_free_tier():
    assert ":free" in DEFAULT_REMOTE_MODEL


def test_set_local_mode_persists(tmp_path):
    set_local_mode(tmp_path)
    loaded = load_inference_profile(tmp_path)
    assert loaded is not None
    assert loaded.mode == InferenceMode.LOCAL


def test_set_remote_byok_mode_persists(tmp_path):
    set_remote_byok_mode("sk-or-v1-test-key-1234567890", workspace_dir=tmp_path)
    loaded = load_inference_profile(tmp_path)
    assert loaded is not None
    assert loaded.mode == InferenceMode.REMOTE_BYOK
    assert should_use_remote_completion(tmp_path) is True


def test_profile_file_is_private(tmp_path):
    profile = set_local_mode(tmp_path)
    path = inference_profile_path(tmp_path)
    assert path.exists()
    assert profile.install_id
