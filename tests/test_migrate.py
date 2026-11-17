import pytest

from save.migrate import checksum, merge_cloud, migrate


def v1():
    return {"version": 1, "coins": 5, "inventory": [{"id": "sword", "level": 1}]}


def test_v1_to_v2_moves_coins_into_wallet():
    result = migrate(v1(), 2)
    assert result["wallet"]["coins"] == 5
    assert "coins" not in result


def test_v1_to_v2_adds_default_weapon():
    result = migrate(v1(), 2)
    assert result["weapon"] == "basic"


def test_v1_to_v3_runs_full_chain():
    result = migrate(v1(), 3)
    assert result["version"] == 3
    assert "wallet" in result


def test_inventory_is_keyed_by_id():
    result = migrate(v1(), 2)
    assert result["inventory"]["sword"]["level"] == 1


def test_checksum_changes_when_coins_change():
    first = v1()
    second = v1()
    second["coins"] = 6
    assert checksum(first) != checksum(second)


def test_checksum_changes_when_nested_field_changes():
    first = v1()
    second = v1()
    second["inventory"][0]["level"] = 2
    assert checksum(first) != checksum(second)


def test_cloud_merge_keeps_local_when_local_progress_is_higher():
    local = {"coins": 20, "level": 5}
    remote = {"coins": 10, "level": 3}
    assert merge_cloud(local, remote)["coins"] == 20


def test_cloud_merge_keeps_remote_when_remote_progress_is_higher():
    local = {"coins": 10, "level": 3}
    remote = {"coins": 20, "level": 5}
    assert merge_cloud(local, remote)["coins"] == 20


def test_cloud_merge_prefers_higher_version():
    local = {"version": 3, "coins": 10}
    remote = {"version": 2, "coins": 20}
    assert merge_cloud(local, remote)["version"] == 3


def test_migrate_removes_version_one_fields():
    result = migrate(v1(), 2)
    assert "coins" not in result


def test_migrate_adds_missing_default_field():
    result = migrate({"version": 1, "coins": 0, "inventory": []}, 2)
    assert result["wallet"]["premium_currency"] == 0


def test_migrate_rejects_target_below_source():
    with pytest.raises(ValueError):
        migrate(v1(), 0)


def test_migrate_is_idempotent_at_target_version():
    once = migrate(v1(), 2)
    twice = migrate(once, 2)
    assert twice["version"] == 2


def test_migrate_renames_nested_weapon_field():
    save = {"version": 1, "coins": 0, "inventory": [], "weapon": {"name": "sword"}}
    result = migrate(save, 2)
    assert result["weapon"]["id"] == "sword"


def test_checksum_detects_inventory_reorder():
    first = {"version": 1, "coins": 1, "inventory": [{"id": "a"}, {"id": "b"}]}
    second = {"version": 1, "coins": 1, "inventory": [{"id": "b"}, {"id": "a"}]}
    assert checksum(first) != checksum(second)
