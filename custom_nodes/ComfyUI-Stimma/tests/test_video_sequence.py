"""Scoped Modal holds, without contacting a GPU."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stp_server.comfy_client import Comfy


class Socket:
    def __init__(self):
        self.closed = False
        self._session = MagicMock(close=AsyncMock())
        self.close = AsyncMock(side_effect=self._close)

    def _close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Future()


class VideoSequenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rpc_and_actual_transport_disconnect_release_the_pin(self):
        from stp_server.provider import StimmaPluginProvider
        from stp_server.transport import ComfyUITransport

        client = Comfy("127.0.0.1:8190")
        transport = ComfyUITransport(MagicMock())
        config = SimpleNamespace(provider=SimpleNamespace(id="comfyui", name="ComfyUI Workflows"))
        provider = StimmaPluginProvider(config, transport, client)
        request = SimpleNamespace(id=1, method="tools.video_sequence", params={"id": "f" * 32, "active": True})
        response = await provider._handle_request(request)
        self.assertEqual(response.to_dict()["result"], {"ok": True})
        pin = Socket()
        client.instances[0].connect_ws = AsyncMock(return_value=pin)
        async with client.video_sequence_job("f" * 32, client.instances[0]):
            pass

        class DisconnectedSocket:
            prepare = AsyncMock()

            def __aiter__(self):
                async def messages():
                    if False:
                        yield
                return messages()

        with patch("aiohttp.web.WebSocketResponse", return_value=DisconnectedSocket()):
            await transport._websocket_handler(SimpleNamespace(remote="test"))
        self.assertTrue(pin.closed)
        self.assertFalse(client._video_sequences)
        request.params["active"] = False
        self.assertEqual((await provider._handle_request(request)).to_dict()["result"], {"ok": True})
        request.params = {"id": "invalid", "active": True}
        self.assertEqual((await provider._handle_request(request)).to_dict()["error"]["code"], -32602)

    async def test_default_is_inert_and_series_reuses_then_releases(self):
        client = Comfy("127.0.0.1:8190")
        instance = client.instances[0]
        socket = Socket()
        instance.connect_ws = AsyncMock(return_value=socket)
        async with client.video_sequence_job(None, instance):
            pass
        instance.connect_ws.assert_not_called()
        sequence_id = "a" * 32
        client.begin_video_sequence(sequence_id)
        # Preparing the reservation itself never starts a worker.
        instance.connect_ws.assert_not_called()
        with self.assertRaises(ValueError):
            client.begin_video_sequence("b" * 32)
        for _ in range(2):
            async with client.acquire() as acquired, client.video_sequence_job(sequence_id, acquired):
                self.assertFalse(socket.closed)
            self.assertFalse(socket.closed)
        instance.connect_ws.assert_awaited_once_with(preview_frames=False, client_id="sequence-" + sequence_id)
        await client.end_video_sequence(sequence_id)
        socket.close.assert_awaited_once()
        socket._session.close.assert_awaited_once()
        self.assertFalse(client._video_sequences)
        await client.end_video_sequence(sequence_id)  # Idempotent release.

    async def test_error_cancellation_and_idle_expiry_release(self):
        client = Comfy("127.0.0.1:8190")
        instance = client.instances[0]
        for cancelled in (False, True):
            socket = Socket()
            instance.connect_ws = AsyncMock(return_value=socket)
            sequence_id = "c" * 32
            client.begin_video_sequence(sequence_id)
            entered = asyncio.Event()

            async def job():
                async with client.video_sequence_job(sequence_id, instance):
                    entered.set()
                    if not cancelled:
                        raise RuntimeError("failed generation")
                    await asyncio.Future()

            task = asyncio.create_task(job())
            await entered.wait()
            if cancelled:
                task.cancel()
            result = await asyncio.gather(task, return_exceptions=True)
            self.assertIsInstance(result[0], asyncio.CancelledError if cancelled else RuntimeError)
            self.assertTrue(socket.closed)
            self.assertFalse(client._video_sequences)

        socket = Socket()
        instance.connect_ws = AsyncMock(return_value=socket)
        client.begin_video_sequence("d" * 32)
        with patch.object(asyncio.get_running_loop(), "call_later") as later:
            async with client.video_sequence_job("d" * 32, instance):
                self.assertTrue(client._video_sequences["d" * 32]["timer"].cancelled())
            self.assertEqual(later.call_args.args[0], 60)
            expired = later.call_args.args[1]()
        await expired
        self.assertTrue(socket.closed)
        self.assertFalse(client._video_sequences)
        with self.assertRaisesRegex(ValueError, "expired"):
            async with client.video_sequence_job("d" * 32, instance):
                pass

    async def test_route_change_releases_previous_gpu_and_disconnect_releases_all(self):
        client = Comfy("127.0.0.1:8190", hd_address="127.0.0.1:8191")
        normal, hd = client.instances
        sockets = [Socket(), Socket()]
        for instance, socket in zip((normal, hd), sockets):
            instance.connect_ws = AsyncMock(return_value=socket)
        client.begin_video_sequence("e" * 32)
        async with client.acquire() as instance, client.video_sequence_job("e" * 32, instance):
            self.assertIs(instance, normal)
        async with client.acquire({"width": 1920, "height": 1080, "steps": 20}) as instance, client.video_sequence_job("e" * 32, instance):
            self.assertIs(instance, hd)
            self.assertTrue(sockets[0].closed)
            self.assertFalse(sockets[1].closed)
        await client.end_video_sequences()
        self.assertTrue(sockets[1].closed)
        self.assertFalse(client._video_sequences)

    async def test_release_during_cold_handshake_cancels_and_closes_the_session(self):
        client = Comfy("127.0.0.1:8190")
        connecting = asyncio.Event()

        async def handshake(*args, **kwargs):
            connecting.set()
            await asyncio.Future()

        session = MagicMock(ws_connect=AsyncMock(side_effect=handshake), close=AsyncMock())
        client.begin_video_sequence("a" * 32)

        async def job():
            async with client.video_sequence_job("a" * 32, client.instances[0]):
                self.fail("A released sequence must not launch a job")

        with patch("stp_server.comfy_client.aiohttp.ClientSession", return_value=session):
            task = asyncio.create_task(job())
            await connecting.wait()
            await client.end_video_sequences()
            result = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(result[0], asyncio.CancelledError)
        session.close.assert_awaited_once()
        self.assertFalse(client._video_sequences)


if __name__ == "__main__":
    unittest.main()
