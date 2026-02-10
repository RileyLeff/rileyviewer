"""Integration tests for the HTTP API endpoints."""

from __future__ import annotations

import base64
import json
import urllib.request
import urllib.error

import pytest


class TestHealth:
    def test_health_returns_ok(self, server):
        url = f"{server.base_url}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200
            assert resp.read().decode() == "ok"


class TestPublish:
    def test_publish_svg(self, server):
        plot_id = server.publish({"type": "Svg", "data": "<svg></svg>"})
        assert isinstance(plot_id, str)
        assert len(plot_id) > 0

    def test_publish_png(self, server):
        # Minimal 1x1 red PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        plot_id = server.publish({"type": "Png", "data": encoded})
        assert isinstance(plot_id, str)

    def test_publish_plotly(self, server):
        plotly_json = json.dumps({"data": [{"x": [1, 2], "y": [3, 4], "type": "scatter"}]})
        plot_id = server.publish({"type": "Plotly", "data": plotly_json})
        assert isinstance(plot_id, str)

    def test_publish_vega(self, server):
        vega_json = json.dumps({
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": [{"x": 1, "y": 2}]},
            "mark": "point",
            "encoding": {"x": {"field": "x"}, "y": {"field": "y"}},
        })
        plot_id = server.publish({"type": "Vega", "data": vega_json})
        assert isinstance(plot_id, str)

    def test_publish_html(self, server):
        plot_id = server.publish({"type": "Html", "data": "<h1>hello</h1>"})
        assert isinstance(plot_id, str)

    def test_publish_csv(self, server):
        plot_id = server.publish({"type": "Csv", "data": "a,b\n1,2\n3,4"})
        assert isinstance(plot_id, str)

    def test_publish_arrow_ipc(self, server):
        import pyarrow as pa
        import pyarrow.ipc
        import io

        table = pa.table({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        sink = io.BytesIO()
        writer = pa.ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()
        encoded = base64.b64encode(sink.getvalue()).decode("ascii")
        plot_id = server.publish({"type": "ArrowIpc", "data": encoded})
        assert isinstance(plot_id, str)

    def test_publish_returns_unique_ids(self, server):
        id1 = server.publish({"type": "Html", "data": "<p>1</p>"})
        id2 = server.publish({"type": "Html", "data": "<p>2</p>"})
        assert id1 != id2


class TestAuth:
    def test_publish_without_token_rejected(self, server):
        payload = json.dumps({"content": {"type": "Html", "data": "x"}}).encode()
        req = urllib.request.Request(
            server.publish_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_publish_with_wrong_token_rejected(self, server):
        payload = json.dumps({
            "content": {"type": "Html", "data": "x"},
            "token": "wrong-token",
        }).encode()
        req = urllib.request.Request(
            server.publish_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_publish_with_valid_token_accepted(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>auth ok</p>"})
        assert isinstance(plot_id, str)


class TestPublishEdgeCases:
    def test_publish_empty_svg(self, server):
        plot_id = server.publish({"type": "Svg", "data": ""})
        assert isinstance(plot_id, str)

    def test_publish_large_csv(self, server):
        # 1000 rows
        rows = ["x,y"] + [f"{i},{i*2}" for i in range(1000)]
        csv_data = "\n".join(rows)
        plot_id = server.publish({"type": "Csv", "data": csv_data})
        assert isinstance(plot_id, str)

    def test_publish_invalid_content_type_rejected(self, server):
        payload = json.dumps({
            "content": {"type": "Invalid", "data": "x"},
            "token": server.token,
        }).encode()
        req = urllib.request.Request(
            server.publish_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 422

    def test_publish_malformed_json_rejected(self, server):
        req = urllib.request.Request(
            server.publish_url,
            data=b"not json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        # Axum returns 400 for malformed JSON, 422 for valid JSON with bad schema
        assert exc_info.value.code in (400, 422)
