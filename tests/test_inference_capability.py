from unittest.mock import patch

from dragonclaw.inference_capability import probe_local_capability


def test_probe_recommends_remote_on_cpu():
    with patch("dragonclaw.inference_capability.detect_device", return_value="cpu"):
        with patch("dragonclaw.inference_capability.runtime_deps_available", return_value=True):
            with patch("dragonclaw.inference_capability._system_ram_gb", return_value=16.0):
                report = probe_local_capability()
    assert report.recommend_remote is True
    assert any("No GPU" in reason for reason in report.reasons)


def test_probe_auto_local_on_capable_machine():
    with patch("dragonclaw.inference_capability.detect_device", return_value="mps"):
        with patch("dragonclaw.inference_capability.runtime_deps_available", return_value=True):
            with patch("dragonclaw.inference_capability._system_ram_gb", return_value=16.0):
                report = probe_local_capability()
    assert report.recommend_remote is False


def test_probe_recommends_remote_without_deps():
    with patch("dragonclaw.inference_capability.detect_device", return_value="mps"):
        with patch("dragonclaw.inference_capability.runtime_deps_available", return_value=False):
            with patch("dragonclaw.inference_capability._system_ram_gb", return_value=16.0):
                report = probe_local_capability()
    assert report.recommend_remote is True
