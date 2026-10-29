import json

from app.export_snapshot import MeterExportSnapshot


def meter(meter_id, status, dt_name):
    return {
        "meterId": meter_id, "serialNo": meter_id + "-SERIAL", "make": "Test",
        "phaseType": "single", "installStatus": status, "installType": "Whole Current",
        "build": "legacy", "dtCode": "DT-001",
        "hierarchy": {
            "dt": {"name": dt_name, "code": "DT-001"},
            "feeder": {"name": "Feeder", "code": "F-001"},
        },
        "geo": {"lat": 26.8, "lng": 75.9},
    }


def test_catalog_search_and_filter(tmp_path):
    path = tmp_path / "meters.json"
    path.write_text(json.dumps([
        meter("J100000", "Installed", "DT One"),
        meter("J100001", "Faulty", "DT One"),
    ]))
    catalog = MeterExportSnapshot(str(path))
    assert catalog.list_meters(10, 0).total == 2
    assert catalog.list_meters(10, 0, status="faulty").total == 1
    assert catalog.list_meters(10, 0, search="J100001").items[0].meter_id == "J100001"
    assert catalog.transformer("DT-001").meter_count == 2


def test_conflicting_transformer_names(tmp_path):
    path = tmp_path / "meters.json"
    path.write_text(json.dumps([
        meter("J100000", "Installed", "DT One"),
        meter("J100001", "Installed", "Different name"),
    ]))
    summary = MeterExportSnapshot(str(path)).transformer("DT-001")
    assert summary.name is None
    assert summary.name_variants == ["DT One", "Different name"]
