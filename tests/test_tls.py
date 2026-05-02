"""Tests for TLS configuration in daemon._run."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import uvicorn


def _build_ssl_kwargs(cfg: dict) -> dict:
    """Replicate daemon._run TLS logic without starting a server."""
    ssl_kwargs = {}
    tls_cert = cfg.get("tls_cert_path", "")
    tls_key = cfg.get("tls_key_path", "")
    if tls_cert and tls_key:
        ssl_kwargs = {
            "ssl_certfile": str(Path(tls_cert).expanduser()),
            "ssl_keyfile": str(Path(tls_key).expanduser()),
        }
    return ssl_kwargs


class TestTLSCertGeneration:
    def test_openssl_generates_cert_and_key(self, tmp_path):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        result = subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "1", "-nodes", "-subj", "/CN=test",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert cert.exists()
        assert key.exists()
        assert cert.stat().st_size > 0
        assert key.stat().st_size > 0


class TestTLSUvicornConfig:
    def test_tls_config_passes_ssl_kwargs(self, tmp_path):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        # Create dummy cert/key files
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "1", "-nodes", "-subj", "/CN=test",
            ],
            capture_output=True,
            check=True,
        )

        cfg = {
            "tls_cert_path": str(cert),
            "tls_key_path": str(key),
        }

        captured_kwargs = {}

        original_config = uvicorn.Config.__init__

        def capture_config(self, app, **kwargs):
            captured_kwargs.update(kwargs)
            # Don't actually initialize — just capture
            pass

        with patch.object(uvicorn.Config, "__init__", capture_config):
            ssl_kwargs = _build_ssl_kwargs(cfg)
            uvicorn.Config("waggle.server:app", host="127.0.0.1", port=8422, **ssl_kwargs)

        assert "ssl_certfile" in captured_kwargs
        assert "ssl_keyfile" in captured_kwargs
        assert captured_kwargs["ssl_certfile"] == str(cert)
        assert captured_kwargs["ssl_keyfile"] == str(key)

    def test_no_tls_config_no_ssl_kwargs(self):
        cfg = {
            "tls_cert_path": "",
            "tls_key_path": "",
        }

        captured_kwargs = {}

        def capture_config(self, app, **kwargs):
            captured_kwargs.update(kwargs)

        with patch.object(uvicorn.Config, "__init__", capture_config):
            ssl_kwargs = _build_ssl_kwargs(cfg)
            uvicorn.Config("waggle.server:app", host="127.0.0.1", port=8422, **ssl_kwargs)

        assert "ssl_certfile" not in captured_kwargs
        assert "ssl_keyfile" not in captured_kwargs

    def test_missing_tls_keys_no_ssl_kwargs(self):
        cfg = {}
        ssl_kwargs = _build_ssl_kwargs(cfg)
        assert ssl_kwargs == {}


class TestTLSDaemonIntegration:
    """Verify daemon._run passes ssl_kwargs to uvicorn.Config."""

    async def _run_daemon(self, tmp_path, extra_cfg):
        """Run daemon._run with a fake uvicorn.Config class; return all Config call kwargs."""
        config_calls = []

        # Replace entire uvicorn.Config with a MagicMock factory that records kwargs
        def mock_config_cls(app, **kwargs):
            obj = MagicMock()
            obj.app = app
            config_calls.append({"app": app, "kwargs": kwargs})
            return obj

        mock_server = MagicMock()
        mock_server.serve = AsyncMock(return_value=None)

        base_cfg = {
            "database_path": str(tmp_path / "state.db"),
            "queue_path": str(tmp_path / "queue.db"),
            "http_port": 8422,
            "tls_cert_path": "",
            "tls_key_path": "",
            "state_poll_interval_seconds": 2,
        }
        base_cfg.update(extra_cfg)

        with patch("waggle.daemon.get_config", return_value=base_cfg), \
             patch("waggle.daemon.get_db_path", return_value=str(tmp_path / "state.db")), \
             patch("waggle.daemon.get_http_port", return_value=8422), \
             patch("waggle.daemon.init_schema"), \
             patch("waggle.rest.set_inbound_queue"), \
             patch("waggle.daemon.get_inbound_queue", return_value=MagicMock()), \
             patch("waggle.daemon.get_outbound_queue", return_value=MagicMock()), \
             patch("waggle.daemon.uvicorn.Config", side_effect=mock_config_cls), \
             patch("waggle.daemon.uvicorn.Server", return_value=mock_server), \
             patch("waggle.daemon.process_inbound", new=AsyncMock(return_value=None)), \
             patch("waggle.daemon.process_outbound", new=AsyncMock(return_value=None)), \
             patch("waggle.daemon.monitor_state", new=AsyncMock(return_value=None)), \
             patch("waggle.daemon.restart_recovery", new=AsyncMock(return_value={})):
            from waggle.daemon import _run
            await _run()

        return config_calls

    @pytest.mark.asyncio
    async def test_daemon_run_with_tls(self, tmp_path):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "1", "-nodes", "-subj", "/CN=test",
            ],
            capture_output=True,
            check=True,
        )

        config_calls = await self._run_daemon(tmp_path, {
            "tls_cert_path": str(cert),
            "tls_key_path": str(key),
        })

        main_call = next((c for c in config_calls if c["app"] == "waggle.server:app"), None)
        assert main_call is not None
        assert main_call["kwargs"].get("ssl_certfile") == str(cert)
        assert main_call["kwargs"].get("ssl_keyfile") == str(key)

    @pytest.mark.asyncio
    async def test_daemon_run_without_tls(self, tmp_path):
        config_calls = await self._run_daemon(tmp_path, {})

        main_call = next((c for c in config_calls if c["app"] == "waggle.server:app"), None)
        assert main_call is not None
        assert "ssl_certfile" not in main_call["kwargs"]
        assert "ssl_keyfile" not in main_call["kwargs"]
