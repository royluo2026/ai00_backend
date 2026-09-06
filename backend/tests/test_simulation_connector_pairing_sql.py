from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib

import pytest

from plugins.simulation.simulation_backend.data import connector_repository
from plugins.simulation.simulation_backend.data.connector_repository import (
    SimulationConnectorRepository,
    SqlPairingRepository,
)
from plugins.simulation.simulation_backend.domain.connector_pairing import PairingError, PairingRecord


NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _record(*, pairing_id="pair-1", installation_id="install-1", version=2):
    return PairingRecord(
        pairing_id=pairing_id, user_code="CODE-1", installation_id=installation_id,
        verifier_hash="a" * 64, device_name="Workstation", runtime_version="1.0.0",
        windows_sid_hash="b" * 64, masked_windows_user="DOMAIN\\u***",
        ephemeral_public_key="unused", status="completing", expires_at=NOW,
        resource_version=version, approved_user_gid="user-1", team_gid="team-1",
        connector_id="connector-1", encrypted_envelope="envelope-1",
        envelope_hash="sha256:envelope-1", activation_challenge_hash="c" * 64,
        activation_status="credential_issued",
    )


def _pairing_row(record):
    return {
        "pairing_id": record.pairing_id, "user_code_display": record.user_code,
        "installation_id": record.installation_id, "verifier_hash": record.verifier_hash,
        "device_name": record.device_name, "runtime_version": record.runtime_version,
        "windows_sid_hash": record.windows_sid_hash,
        "masked_windows_user": record.masked_windows_user,
        "ephemeral_public_key": record.ephemeral_public_key, "status": record.status,
        "expires_at": record.expires_at, "resource_version": record.resource_version,
        "approved_user_gid": record.approved_user_gid, "team_gid": record.team_gid,
        "connector_id": record.connector_id,
        "credential_envelope_json": {"ciphertext": record.encrypted_envelope},
        "credential_envelope_hash": record.envelope_hash,
        "activation_challenge_hash": record.activation_challenge_hash,
        "activation_status": record.activation_status,
    }


def _bootstrap_row(record, status="credential_issued"):
    return {
        "bootstrap_id": "bootstrap-1", "owner_user_gid": "user-1", "team_gid": "team-1",
        "token_hash": "e" * 64, "status": status, "pairing_id": record.pairing_id,
        "expires_at": NOW, "resource_version": 3,
    }


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self._row = None

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        self.connection.queries.append(normalized)
        self.rowcount = 0
        if normalized.startswith("select") and "connector_pairings" in normalized:
            self._row = self.connection.pairings.get(params[0])
        elif normalized.startswith("select") and "connector_pairing_bootstraps" in normalized:
            self._row = next((
                row for row in self.connection.bootstraps.values()
                if row["pairing_id"] == params[0] or row["bootstrap_id"] == params[0] or row["token_hash"] == params[0]
            ), None)
        elif normalized.startswith("select") and "connector_bindings" in normalized:
            self._row = (
                self.connection.bindings.get(params[0])
                if "where connector_id=%s" in normalized
                else next(
                    (
                        row for row in self.connection.bindings.values()
                        if row["owner_user_gid"] == params[0]
                        and (len(params) == 1 or row.get("team_gid") == params[1])
                    ), None,
                )
            )
        elif normalized.startswith("insert into workmanship_sim_connector_bindings"):
            binding = {
                "connector_id": params[0], "owner_user_gid": params[1], "team_gid": params[2],
                "installation_id": params[3], "windows_sid_hash": params[4],
                "display_name": params[5], "runtime_version": params[6], "token_hash": params[7],
                "status": "pending_activation", "pending_pairing_id": params[8],
            }
            if any(
                row["owner_user_gid"] == binding["owner_user_gid"]
                or row["installation_id"] == binding["installation_id"]
                for row in self.connection.bindings.values()
            ):
                raise self.connection.integrity_error()
            self.connection.bindings[binding["connector_id"]] = binding
            self.rowcount = 1
        elif normalized.startswith("insert into workmanship_sim_connector_pairings"):
            if params[0] in self.connection.pairings:
                raise self.connection.integrity_error()
            self.connection.pairings[params[0]] = {"pairing_id": params[0]}
            self.rowcount = 1
        elif "set status='claimed'" in normalized and "connector_pairing_bootstraps" in normalized:
            row = self.connection.bootstraps.get(params[1])
            if (
                not self.connection.fail_bootstrap_update and row
                and row["status"] == "created" and row["resource_version"] == params[2]
            ):
                row.update({"status": "claimed", "pairing_id": params[0], "resource_version": row["resource_version"] + 1})
                self.rowcount = 1
        elif "set status='approved'" in normalized and "connector_pairings" in normalized:
            row = self.connection.pairings.get(params[3])
            if row and row["status"] == "pending" and row["resource_version"] == params[4]:
                row.update({
                    "status": "approved", "resource_version": params[0],
                    "approved_user_gid": params[1], "team_gid": params[2],
                })
                self.rowcount = 1
        elif "set status='completing'" in normalized:
            row = self.connection.pairings.get(params[5])
            if not self.connection.fail_pairing_update and row and row["status"] == "approved" and row["resource_version"] == params[7]:
                row.update({
                    "status": "completing", "resource_version": params[0], "connector_id": params[1],
                    "credential_envelope_json": params[2], "credential_envelope_hash": params[3],
                    "activation_challenge_hash": params[4], "activation_status": "credential_issued",
                })
                self.rowcount = 1
        elif "set status='completed'" in normalized:
            row = self.connection.pairings.get(params[1])
            if row and row["status"] == "completing" and row["activation_status"] == "credential_issued" and row["resource_version"] == params[3]:
                row.update({"status": "completed", "activation_status": "active", "resource_version": params[0]})
                self.rowcount = 1
        elif "update workmanship_sim_connector_pairing_bootstraps" in normalized:
            row = self.connection.bootstraps.get(params[0])
            expected_version = params[1] if len(params) > 1 else row["resource_version"]
            assignment = normalized.split(" where ", 1)[0]
            expected_status = (
                "claimed" if "status='approved'" in assignment
                else "approved" if "status='credential_issued'" in assignment
                else "credential_issued" if "status='active'" in assignment
                else row["status"]
            )
            next_status = (
                "approved" if "status='approved'" in assignment
                else "credential_issued" if "status='credential_issued'" in assignment
                else "active" if "status='active'" in assignment
                else row["status"]
            )
            if (
                not self.connection.fail_bootstrap_update and row
                and row["status"] == expected_status and row["resource_version"] == expected_version
            ):
                row.update({"status": next_status, "resource_version": row["resource_version"] + 1})
                self.rowcount = 1
        elif "set team_gid=" in normalized:
            row = self.connection.bindings.get(params[6])
            if row and row["owner_user_gid"] == params[7] and row["installation_id"] == params[8]:
                row.update({"team_gid": params[0], "windows_sid_hash": params[1], "display_name": params[2], "runtime_version": params[3], "token_hash": params[4], "pending_pairing_id": params[5], "status": "pending_activation"})
                self.rowcount = 1
        elif "update workmanship_sim_connector_bindings" in normalized:
            row = self.connection.bindings.get(params[0])
            if row and row["status"] == "pending_activation" and row.get("pending_pairing_id") == params[2]:
                row["status"] = "offline"
                row["pending_pairing_id"] = None
                self.rowcount = 1

    def fetchone(self):
        return deepcopy(self._row) if self._row else None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, record, *, fail_pairing_update=False, fail_bootstrap_update=False):
        self.pairings = {record.pairing_id: _pairing_row(record)}
        self.bootstraps = {"bootstrap-1": _bootstrap_row(record)}
        self.bindings = {}
        self.fail_pairing_update = fail_pairing_update
        self.fail_bootstrap_update = fail_bootstrap_update
        self.queries = []

    @staticmethod
    def integrity_error():
        from pymysql.err import IntegrityError
        return IntegrityError(1062, "duplicate")

    def cursor(self):
        return _Cursor(self)

    @contextmanager
    def transaction(self):
        snapshot = (deepcopy(self.pairings), deepcopy(self.bindings), deepcopy(self.bootstraps))
        try:
            yield self
        except Exception:
            self.pairings, self.bindings, self.bootstraps = snapshot
            raise


@pytest.fixture
def sql_repository(monkeypatch):
    connection = _Connection(_record())

    @contextmanager
    def get_connection():
        with connection.transaction() as transaction:
            yield transaction

    monkeypatch.setattr(connector_repository, "get_simulation_conn", get_connection)
    return SqlPairingRepository(), connection


def _binding(installation_id="install-1"):
    return {
        "connector_id": "connector-1", "installation_id": installation_id, "team_gid": "team-1",
        "windows_sid_hash": "b" * 64, "display_name": "Workstation",
        "runtime_version": "1.0.0", "token_hash": "d" * 64,
        "pending_pairing_id": "pair-1",
    }


def test_request_creates_pairing_and_claims_bootstrap_in_one_transaction(sql_repository):
    repository, connection = sql_repository
    connection.pairings.clear()
    connection.bootstraps["bootstrap-1"].update({
        "status": "created", "pairing_id": None, "resource_version": 1,
        "expires_at": datetime(2026, 9, 7, tzinfo=UTC),
    })

    bootstrap = repository.create_pairing_from_bootstrap("e" * 64, NOW, _record())

    assert "pair-1" in connection.pairings
    assert bootstrap.status == "claimed"
    assert connection.bootstraps["bootstrap-1"]["pairing_id"] == "pair-1"


def test_approval_updates_pairing_and_bootstrap_in_one_transaction(sql_repository):
    repository, connection = sql_repository
    pending = _record(version=1)
    pending.status = "pending"
    pending.activation_status = "not_issued"
    connection.pairings["pair-1"] = _pairing_row(pending)
    connection.bootstraps["bootstrap-1"].update({"status": "claimed", "resource_version": 2})
    approved = _record(version=2)
    approved.status = "approved"
    approved.activation_status = "not_issued"

    repository.approve_pairing(approved, expected_version=1)

    assert connection.pairings["pair-1"]["status"] == "approved"
    assert connection.bootstraps["bootstrap-1"]["status"] == "approved"


def test_issue_replay_reuses_the_same_binding_and_locks_the_pairing(sql_repository):
    repository, connection = sql_repository
    record = _record()
    connection.pairings["pair-1"].update({"status": "approved", "activation_status": "not_issued", "resource_version": 1})
    connection.bootstraps["bootstrap-1"].update({"status": "approved", "resource_version": 2})

    first = repository.issue_credential(record, "user-1", _binding())
    replay = repository.issue_credential(record, "user-1", _binding())

    assert replay.envelope_hash == first.envelope_hash
    assert list(connection.bindings) == ["connector-1"]
    assert connection.pairings["pair-1"]["credential_envelope_hash"] == "sha256:envelope-1"
    assert connection.bootstraps["bootstrap-1"]["status"] == "credential_issued"
    assert any("for update" in query for query in connection.queries)


def test_issue_for_a_conflicting_installation_returns_a_stable_error(sql_repository):
    repository, connection = sql_repository
    connection.pairings["pair-1"].update({"status": "approved", "activation_status": "not_issued", "resource_version": 1})
    connection.bootstraps["bootstrap-1"].update({"status": "approved", "resource_version": 2})
    connection.bindings["connector-existing"] = {"connector_id": "connector-existing", "owner_user_gid": "user-1", "installation_id": "install-2", "status": "offline"}

    with pytest.raises(PairingError, match="connector_binding_conflict"):
        repository.issue_credential(_record(), "user-1", _binding())

    assert connection.pairings["pair-1"]["status"] == "approved"
    assert list(connection.bindings) == ["connector-existing"]


def test_concurrent_activation_allows_only_one_transition(sql_repository):
    repository, connection = sql_repository
    connection.bindings["connector-1"] = {"connector_id": "connector-1", "owner_user_gid": "user-1", "installation_id": "install-1", "team_gid": "team-1", "pending_pairing_id": "pair-1", "status": "pending_activation"}
    record = _record()

    repository.activate_pairing(record, expected_version=2)
    with pytest.raises(PairingError, match="pairing_version_conflict"):
        repository.activate_pairing(record, expected_version=2)

    assert connection.pairings["pair-1"]["activation_status"] == "active"
    assert connection.bindings["connector-1"]["status"] == "offline"
    assert connection.bootstraps["bootstrap-1"]["status"] == "active"


def test_old_pairing_cannot_activate_the_binding_generation_for_a_new_pairing(sql_repository):
    repository, connection = sql_repository
    connection.bindings["connector-1"] = {
        "connector_id": "connector-1", "owner_user_gid": "user-1",
        "installation_id": "install-1", "team_gid": "team-1",
        "pending_pairing_id": "pair-2", "status": "pending_activation",
    }

    with pytest.raises(PairingError, match="connector_binding_conflict"):
        repository.activate_pairing(_record(), expected_version=2)

    assert connection.pairings["pair-1"]["activation_status"] == "credential_issued"
    assert connection.bindings["connector-1"]["pending_pairing_id"] == "pair-2"
    assert connection.bootstraps["bootstrap-1"]["status"] == "credential_issued"


def test_binding_lookup_is_scoped_to_user_and_team(sql_repository):
    repository, connection = sql_repository
    connection.bindings["connector-1"] = {
        **_binding(), "owner_user_gid": "user-1", "status": "offline",
    }

    assert repository.binding_for_user("user-1", "team-1")["connector_id"] == "connector-1"
    assert repository.binding_for_user("user-1", "team-2") is None


def test_issue_rolls_back_insert_when_the_pairing_update_loses_its_race(monkeypatch):
    record = _record()
    record.status = "approved"
    record.activation_status = "not_issued"
    record.resource_version = 1
    connection = _Connection(record, fail_pairing_update=True)
    connection.bootstraps["bootstrap-1"].update({"status": "approved", "resource_version": 2})

    @contextmanager
    def get_connection():
        with connection.transaction() as transaction:
            yield transaction

    monkeypatch.setattr(connector_repository, "get_simulation_conn", get_connection)
    with pytest.raises(PairingError, match="pairing_version_conflict"):
        SqlPairingRepository().issue_credential(record, "user-1", _binding())

    assert connection.bindings == {}
    assert connection.pairings["pair-1"]["status"] == "approved"


def test_issue_rolls_back_pairing_and_binding_when_bootstrap_transition_loses_its_race(monkeypatch):
    approved = _record()
    approved.status = "approved"
    approved.activation_status = "not_issued"
    approved.resource_version = 1
    connection = _Connection(approved, fail_bootstrap_update=True)
    connection.bootstraps["bootstrap-1"].update({"status": "approved", "resource_version": 2})
    issued = _record()

    @contextmanager
    def get_connection():
        with connection.transaction() as transaction:
            yield transaction

    monkeypatch.setattr(connector_repository, "get_simulation_conn", get_connection)
    with pytest.raises(PairingError, match="pairing_bootstrap_version_conflict"):
        SqlPairingRepository().issue_credential(issued, "user-1", _binding())

    assert connection.bindings == {}
    assert connection.pairings["pair-1"]["status"] == "approved"
    assert connection.bootstraps["bootstrap-1"]["status"] == "approved"


def test_issued_credential_cannot_authenticate_until_activation_and_rotation_revokes_old_token(sql_repository):
    pairing_repository, connection = sql_repository
    record = _record()
    connection.pairings["pair-1"].update({"status": "approved", "activation_status": "not_issued", "resource_version": 1})
    connection.bootstraps["bootstrap-1"].update({"status": "approved", "resource_version": 2})
    binding = _binding()
    binding["token_hash"] = hashlib.sha256(b"new-token").hexdigest()
    connection.bindings["connector-1"] = {
        **_binding(), "owner_user_gid": "user-1", "token_hash": hashlib.sha256(b"old-token").hexdigest(),
        "status": "online",
    }

    pairing_repository.issue_credential(record, "user-1", binding)

    assert connection.bindings["connector-1"]["status"] == "pending_activation"
    assert connection.bindings["connector-1"]["token_hash"] == binding["token_hash"]
    with pytest.raises(PermissionError, match="invalid_connector_credentials"):
        SimulationConnectorRepository().authenticate_connector("connector-1", "new-token")
    with pytest.raises(PermissionError, match="invalid_connector_credentials"):
        SimulationConnectorRepository().authenticate_connector("connector-1", "old-token")
    pairing_repository.activate_pairing(record, expected_version=2)

    assert SimulationConnectorRepository().authenticate_connector("connector-1", "new-token")["status"] == "offline"
    with pytest.raises(PermissionError, match="invalid_connector_credentials"):
        SimulationConnectorRepository().authenticate_connector("connector-1", "old-token")
