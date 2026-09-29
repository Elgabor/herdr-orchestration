"""Conservative usage samples and private account-scoped cache."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from .contracts import ContractError, HARNESSES, ID, SCHEMA_VERSION, validate_metric
from .state import StateStore, _atomic_json, _read_json

METRICS = ("session_usage", "rate_limit", "plan_quota", "api_balance", "price_input", "price_output")
DEFAULT_TTL_SECONDS = 300


def validate_profile(value: object) -> dict:
    if not isinstance(value, dict):
        raise ContractError("profile: expected object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("profile.schema_version: unsupported")
    if not isinstance(value.get("profile_id"), str) or not ID.fullmatch(value["profile_id"]):
        raise ContractError("profile.profile_id: invalid")
    if value.get("harness") not in HARNESSES:
        raise ContractError("profile.harness: unsupported")
    for key in ("version", "provider", "account_ref", "auth_mode", "model_id", "source"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ContractError(f"profile.{key}: required nonempty string")
    if type(value.get("authorized")) is not bool:
        raise ContractError("profile.authorized: expected bool")
    if not isinstance(value.get("effort"), str) or not value["effort"].strip():
        raise ContractError("profile.effort: required")
    return value


def validate_usage_sample(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("usage_sample: expected schema version 1 object")
    for key in ("profile_id", "provider", "account_ref", "read_at", "reader"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ContractError(f"usage_sample.{key}: required")
    if value.get("harness") not in HARNESSES or not isinstance(value.get("version"), str):
        raise ContractError("usage_sample: harness/version required")
    if not isinstance(value.get("auth_mode"), str) or not value["auth_mode"]:
        raise ContractError("usage_sample.auth_mode: required")
    models = value.get("models")
    if not isinstance(models, dict) or models.get("state") not in {"known", "unknown", "unavailable", "stale"}:
        raise ContractError("usage_sample.models: state required")
    if not isinstance(models.get("items"), list) or (models["state"] != "known" and models["items"]):
        raise ContractError("usage_sample.models: unknown list must be empty")
    if not isinstance(models.get("source"), str) or not models["source"]:
        raise ContractError("usage_sample.models.source: required")
    try:
        observed = datetime.fromisoformat(value["read_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("usage_sample.read_at: invalid timestamp") from error
    if observed.tzinfo is None:
        raise ContractError("usage_sample.read_at: timezone required")
    metrics = value.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
        raise ContractError("usage_sample.metrics: missing or extra metric")
    for metric in metrics.values():
        validate_metric(metric)
    return value


def _timestamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unknown(scope: str, source: str, now: datetime, state: str = "unknown") -> dict:
    return {"state": state, "value": None, "unit": "unknown", "scope": scope,
            "observed_at": _timestamp(now), "source": source}


def unknown_sample(profile: dict, now: datetime | None = None) -> dict:
    validate_profile(profile)
    now = now or datetime.now(timezone.utc)
    source = "no certified non-invasive quota reader for this profile"
    metrics = {"session_usage": _unknown("session", source, now),
               "rate_limit": _unknown("model/account", source, now),
               "plan_quota": _unknown("plan/account", source, now),
               "api_balance": _unknown("API account", source, now),
               "price_input": _unknown("model; per million input tokens", source, now),
               "price_output": _unknown("model; per million output tokens", source, now)}
    sample = {"schema_version": SCHEMA_VERSION, "profile_id": profile["profile_id"],
              "harness": profile["harness"], "version": profile["version"],
              "provider": profile["provider"], "account_ref": profile["account_ref"],
              "auth_mode": profile["auth_mode"],
              "models": {"state": "unknown", "items": [], "source": source},
              "read_at": _timestamp(now), "reader": "none", "metrics": metrics}
    return validate_usage_sample(sample)


def cache_key(profile: dict) -> str:
    validate_profile(profile)
    fields = ("harness", "version", "provider", "account_ref", "auth_mode", "model_id", "effort")
    identity = json.dumps([profile[key] for key in fields], separators=(",", ":"))
    return hashlib.sha256(identity.encode()).hexdigest()


def _age_seconds(sample: dict, now: datetime) -> float:
    observed = datetime.fromisoformat(sample["read_at"].replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ContractError("usage_sample.read_at: timezone required")
    return (now - observed).total_seconds()


def read_quota(profile: dict, store: StateStore, *, now: datetime | None = None,
               ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    """Return a fresh cached sample, otherwise a truthful unknown sample.

    No UI command, session-store read, account request, or login is attempted.
    A future certified reader may put a sample into this cache explicitly.
    """
    validate_profile(profile)
    if not 1 <= ttl_seconds <= 3600:
        raise ContractError("ttl_seconds: expected 1..3600")
    now = now or datetime.now(timezone.utc)
    key = cache_key(profile)
    with store._locked():
        path = store.root / "quota-cache.json"
        cache = _read_json(path) if path.exists() or path.is_symlink() else {}
        entry = cache.get(key)
        if entry:
            sample = validate_usage_sample(entry["sample"])
            if (sample["profile_id"], sample["harness"], sample["version"], sample["provider"],
                sample["account_ref"], sample["auth_mode"]) != (
                profile["profile_id"], profile["harness"], profile["version"], profile["provider"],
                profile["account_ref"], profile["auth_mode"]
            ):
                raise ContractError("quota cache: profile identity mismatch")
            age = _age_seconds(sample, now)
            if 0 <= age <= ttl_seconds:
                return {"sample": sample, "cache": "fresh", "ttl_seconds": ttl_seconds}
            stale = {**sample, "models": {**sample["models"], "state": "stale", "items": []}, "metrics": {
                name: {**metric, "state": "stale", "value": None}
                for name, metric in sample["metrics"].items()}}
            return {"sample": validate_usage_sample(stale), "cache": "stale", "ttl_seconds": ttl_seconds}
    return {"sample": unknown_sample(profile, now), "cache": "miss", "ttl_seconds": ttl_seconds}


def cache_sample(profile: dict, sample: dict, store: StateStore) -> None:
    """Input seam for a certified native reader; fixture tests use this offline."""
    validate_profile(profile)
    validate_usage_sample(sample)
    if sample["profile_id"] != profile["profile_id"]:
        raise ContractError("usage_sample: selected profile mismatch")
    if (sample["profile_id"], sample["harness"], sample["version"], sample["provider"],
        sample["account_ref"], sample["auth_mode"]) != (
        profile["profile_id"], profile["harness"], profile["version"], profile["provider"],
        profile["account_ref"], profile["auth_mode"]
    ):
        raise ContractError("usage_sample: profile identity mismatch")
    key = cache_key(profile)
    with store._locked():
        path = store.root / "quota-cache.json"
        cache = _read_json(path) if path.exists() or path.is_symlink() else {}
        cache[key] = {"sample": sample}
        _atomic_json(path, cache)


def validate_catalog(value: object) -> list[dict]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("catalog: expected schema version 1 object")
    profiles = value.get("profiles")
    if not isinstance(profiles, list) or not profiles or len(profiles) > 32:
        raise ContractError("catalog.profiles: expected 1..32 profiles")
    ids = set()
    for profile in profiles:
        validate_profile(profile)
        if profile["profile_id"] in ids:
            raise ContractError("catalog.profile_id: duplicate")
        ids.add(profile["profile_id"])
    return profiles


def check_choice(profile: dict, sample: dict, *, mode: str) -> dict:
    """Check an owner-selected configuration; never silently substitute it."""
    validate_profile(profile)
    validate_usage_sample(sample)
    if sample["profile_id"] != profile["profile_id"] or sample["account_ref"] != profile["account_ref"]:
        raise ContractError("usage_sample: selected profile or account mismatch")
    if mode not in {"explicit", "existing", "auto_authorized"}:
        raise ContractError("selection mode: invalid")
    if not profile["authorized"]:
        return {"outcome": "blocked", "reason": "profile is not authorized", "profile_id": profile["profile_id"]}
    limits = [name for name in ("rate_limit", "plan_quota", "api_balance")
              if sample["metrics"][name]["state"] != "known"]
    if mode == "auto_authorized" and (limits or any(sample["metrics"][name]["state"] != "known"
                                                    for name in ("price_input", "price_output"))):
        return {"outcome": "needs_info", "reason": "automatic cost comparison lacks comparable verified data",
                "profile_id": profile["profile_id"], "unknown": limits}
    return {"outcome": "eligible_with_uncertainty" if limits else "eligible",
            "reason": "owner-selected profile retained; unknown limits are not zero or unlimited",
            "profile_id": profile["profile_id"], "unknown": limits}
