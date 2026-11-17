"""Save migration, checksum, and cloud-merge utilities.

Design notes:
- Migrations run as a version chain (v1 -> v2 -> v3 ...), one step at a
  time, so minor-version upgrades walk the full chain instead of jumping.
- Each step is a pure function: it receives a deep-copied save and returns
  the next-version save. The caller's object is never mutated, and a
  failure mid-chain leaves the original untouched (transactional).
- Field renames are handled by explicit per-step mapping tables.
- Inventory lists are re-keyed by item id so length/order changes never
  silently drop items.
- Unknown fields (e.g. mod data) are preserved across migration.
- Checksums are computed over a canonical serialization (sorted keys) so
  dict insertion order does not matter, while list order and nested
  values do.
"""

import copy
import hashlib
import json

CURRENT_VERSION = 3


# ---------------------------------------------------------------------------
# Migration steps
# ---------------------------------------------------------------------------

def _migrate_v1_to_v2(save):
    """v1 -> v2.

    - ``coins`` moves into ``wallet.coins``; ``wallet.premium_currency``
      defaults to 0.
    - ``weapon`` defaults to ``"basic"``; a legacy dict form
      ``{"name": ...}`` is renamed to ``{"id": ...}``.
    - ``inventory`` (list of items) is re-keyed by item id.
    """
    out = save

    # coins -> wallet.coins (field mapping), with defaults for new fields.
    wallet = dict(out.get("wallet") or {})
    if "coins" in out:
        wallet.setdefault("coins", out.pop("coins"))
    wallet.setdefault("coins", 0)
    wallet.setdefault("premium_currency", 0)
    out["wallet"] = wallet

    # weapon: default, plus rename of legacy nested field name -> id.
    weapon = out.get("weapon", "basic")
    if isinstance(weapon, dict):
        renamed = {}
        for key, value in weapon.items():
            renamed["id" if key == "name" else key] = value
        weapon = renamed
    out["weapon"] = weapon

    # inventory: align by id instead of truncating by position.
    inventory = out.get("inventory", [])
    if isinstance(inventory, list):
        keyed = {}
        for item in inventory:
            if isinstance(item, dict) and "id" in item:
                entry = {k: v for k, v in item.items() if k != "id"}
                keyed[item["id"]] = entry
        out["inventory"] = keyed

    out["version"] = 2
    return out


def _migrate_v2_to_v3(save):
    """v2 -> v3.

    Ensures the wallet block introduced in v2 is complete; unknown fields
    are carried through untouched.
    """
    out = save
    wallet = dict(out.get("wallet") or {})
    wallet.setdefault("coins", 0)
    wallet.setdefault("premium_currency", 0)
    out["wallet"] = wallet
    out["version"] = 3
    return out


_MIGRATION_CHAIN = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def migrate(save, target_version):
    """Migrate ``save`` to ``target_version`` along the version chain.

    Idempotent: migrating a save already at ``target_version`` returns an
    equivalent copy. Raises ``ValueError`` if the target is below the
    source version or no migration path exists. Never mutates the input;
    on failure the original save is left intact (transactional).
    """
    if not isinstance(save, dict):
        raise ValueError("save must be a dict")

    source_version = save.get("version", 1)
    if target_version < source_version:
        raise ValueError(
            "cannot migrate backwards: source v%s > target v%s"
            % (source_version, target_version)
        )
    if target_version > CURRENT_VERSION:
        raise ValueError("unknown target version: %s" % target_version)

    # Work on a deep copy: the caller's save is never half-written.
    working = copy.deepcopy(save)
    version = source_version
    while version < target_version:
        step = _MIGRATION_CHAIN.get(version)
        if step is None:
            raise ValueError("no migration path from v%s" % version)
        working = step(working)
        version = working.get("version", version + 1)
    return working


def _canonical(save):
    """Canonical serialization: mapping keys sorted, list order kept."""
    if isinstance(save, dict):
        return {k: _canonical(save[k]) for k in sorted(save, key=repr)}
    if isinstance(save, (list, tuple)):
        return [_canonical(item) for item in save]
    return save


def checksum(save):
    """Checksum over normalized fields.

    Sensitive to nested values and to list ordering (e.g. inventory
    reorder), insensitive to dict insertion order. Excludes any embedded
    ``checksum`` field so a save can carry its own checksum.
    """
    payload = {k: v for k, v in save.items() if k != "checksum"}
    blob = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), default=repr
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _progress_key(save):
    """Higher means more progress: level first, then coins."""
    wallet = save.get("wallet") if isinstance(save.get("wallet"), dict) else {}
    coins = save.get("coins", wallet.get("coins", 0))
    return (save.get("level", 0), coins)


def merge_cloud(local, remote):
    """Resolve a cloud conflict by version, then by progress.

    A higher save version always wins (newer schema, already migrated).
    Within the same version the save with more progress (level, then
    coins) wins, so a stale remote never overwrites further-along local
    progress. Returns a copy of the winning save.
    """
    local_version = local.get("version", 0)
    remote_version = remote.get("version", 0)
    if local_version != remote_version:
        winner = local if local_version > remote_version else remote
    else:
        winner = (
            local
            if _progress_key(local) >= _progress_key(remote)
            else remote
        )
    return copy.deepcopy(winner)
