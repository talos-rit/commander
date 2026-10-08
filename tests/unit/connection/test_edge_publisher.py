from src.connection.edge_publisher import EdgePublisher

def test_edge_publisher_reuses_icd_payload_without_opening_operator_tcp(monkeypatch):
    calls = []
    def request(url, method="GET", body=None):
        calls.append((url, method, body))
        if url.endswith("/status"):
            return {"operator_connected": True, "joint_counts": [1, 2, 3, 4, 5], "telemetry_age_s": 0.2}
        return {"dispatched": True}
    monkeypatch.setattr("src.connection.edge_publisher.request_json", request)
    monkeypatch.setattr("threading.Thread.start", lambda self: None)
    publisher = EdgePublisher("http://pi:5051")
    publisher.polar_pan_continuous_start(1, 0)
    assert calls[-1][2] == {"command": 3, "payload_hex": "0100"}
    publisher.erv_set_speed_percent(20)
    assert calls[-1][2] == {"command": 8, "payload_hex": "050000000014"}
    publisher.home(1000)
    assert calls[-1][2] == {"command": 2, "payload_hex": "000003e8"}
    assert not hasattr(publisher.operator_connection, "socket")
