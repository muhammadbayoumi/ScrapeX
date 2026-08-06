"""Two machines, one warehouse, and no server to arbitrate between them.

Decision 3: one device at a time, with restore. Drive is enough — no server, no
shared SQLite file over a network — and a lease is the whole of what stops two
machines writing the same warehouse and silently forking its history.

A LEASE AND NOT A LOCK. A lock is held until released, and the machine holding
this one can be closed, unplugged or reinstalled. Nobody would ever release it
and the owner would be locked out of his own data by a laptop that no longer
exists. A lease expires, so the worst case is "wait", not "lose everything".

RENEWED AND NOT TAKEN ONCE. muqawil's details crawl ran 34 hours. A lease long
enough to cover that leaves a crashed machine holding the warehouse for a day
and a half; a lease short enough to recover from a crash quickly expires in the
middle of the crawl. Renewing while working settles both.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scrapex import lease

LAPTOP = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DESKTOP = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def at(minutes: int) -> datetime:
    """A fixed clock. Every instant in these tests is stated, because a test
    that takes the real one is a test that fails for six hours a year."""
    return datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)


@pytest.fixture()
def lease_file(tmp_path):
    return tmp_path / "lease.json"


def test_an_unclaimed_warehouse_is_taken_without_argument(lease_file):
    verdict = lease.may_write(lease_file, LAPTOP, "Windows · laptop", now=at(0))

    assert verdict.allowed
    assert verdict.lease.device == LAPTOP
    assert lease_file.is_file()


def test_a_second_device_is_refused_and_told_who_and_how_long(lease_file):
    """THE CASE THE MILESTONE IS NAMED FOR.

    "Locked" with no idea by whom or for how long is the same dead end as an
    engine that refuses on a stderr nobody reads. The refusal names the machine
    and the wait.
    """
    lease.may_write(lease_file, LAPTOP, "Windows · laptop", now=at(0))

    verdict = lease.may_write(lease_file, DESKTOP, "Windows · desktop", now=at(1))

    assert not verdict.allowed
    assert "laptop" in verdict.reason, "the owner cannot tell which machine to stop"
    assert "14 minutes" in verdict.action, verdict.action
    assert verdict.lease.device == LAPTOP


def test_the_holder_renews_rather_than_fighting_itself(lease_file):
    """Renewing is the same call as taking. Making it separate is how a long
    crawl ends up holding a lease it forgot to keep."""
    first = lease.may_write(lease_file, LAPTOP, now=at(0))

    later = lease.may_write(lease_file, LAPTOP, now=at(5))

    assert later.allowed
    assert later.lease.taken_at == first.lease.taken_at, (
        "renewing restarted the clock on when this device took the warehouse")
    assert later.lease.expires_at > first.lease.expires_at


def test_a_crawl_that_outlives_the_term_keeps_the_warehouse(lease_file):
    """34 hours of muqawil details, renewed every five minutes."""
    lease.may_write(lease_file, LAPTOP, now=at(0))
    for minute in range(5, 34 * 60, lease.RENEW_MINUTES):
        assert lease.may_write(lease_file, LAPTOP, now=at(minute)).allowed

    # And the other machine was refused the whole way through.
    assert not lease.may_write(lease_file, DESKTOP, now=at(34 * 60 - 1)).allowed


def test_a_machine_that_died_does_not_hold_the_warehouse_for_ever(lease_file):
    """THE RECOVERY PATH, and it needs nothing from the dead machine.

    This is why it is a lease. The laptop is gone — reinstalled, stolen, at the
    bottom of a lake — and the desktop takes over by waiting, not by asking.
    """
    lease.may_write(lease_file, LAPTOP, "Windows · laptop", now=at(0))

    refused = lease.may_write(lease_file, DESKTOP, now=at(lease.LEASE_MINUTES - 1))
    taken = lease.may_write(lease_file, DESKTOP, "Windows · desktop",
                            now=at(lease.LEASE_MINUTES))

    assert not refused.allowed
    assert taken.allowed
    assert taken.lease.device == DESKTOP
    assert lease.read(lease_file).device == DESKTOP


def test_a_clean_stop_hands_the_warehouse_over_at_once(lease_file):
    """Waiting fifteen minutes after closing ScrapeX on purpose would be the
    product punishing the owner for being tidy."""
    lease.may_write(lease_file, LAPTOP, now=at(0))

    assert lease.release(lease_file, LAPTOP)
    assert lease.may_write(lease_file, DESKTOP, now=at(1)).allowed


def test_a_device_that_lost_the_lease_cannot_release_the_one_that_took_it(lease_file):
    """The laptop wakes from sleep long after its lease expired and tidies up
    on the way out. Without this it would delete the desktop's lease and both
    machines would be writing."""
    lease.may_write(lease_file, LAPTOP, now=at(0))
    lease.may_write(lease_file, DESKTOP, now=at(lease.LEASE_MINUTES))

    assert not lease.release(lease_file, LAPTOP)
    assert lease.read(lease_file).device == DESKTOP


def test_a_lease_nobody_can_read_is_treated_as_gone(lease_file):
    """A half-written or corrupted file must not hold the warehouse for ever.

    The dangerous reading is the opposite one: `from_json` returning None for a
    torn file means "nobody holds this", and a reader arriving mid-write would
    take a lease somebody else has. That is why the file is written whole and
    moved into place — see the next test.
    """
    lease_file.write_text("{ this is not json", encoding="utf-8")

    assert lease.read(lease_file) is None
    assert lease.may_write(lease_file, DESKTOP, now=at(0)).allowed


def test_a_lease_with_an_unreadable_expiry_is_already_expired(lease_file):
    """Not "held for ever". A malformed expiry cannot be trusted to arrive."""
    lease_file.write_text(json.dumps(
        {"device": LAPTOP, "expires_at": "whenever"}), encoding="utf-8")

    assert lease.read(lease_file).expired(at(0))
    assert lease.may_write(lease_file, DESKTOP, now=at(0)).allowed


def test_the_file_is_written_whole_and_never_seen_half_finished(lease_file):
    """A reader arriving mid-write must not find half a lease — `from_json`
    would call it garbage, which reads as "nobody holds this", which is the one
    wrong answer here."""
    lease.may_write(lease_file, LAPTOP, now=at(0))

    assert not list(lease_file.parent.glob("*.partial")), (
        "a partial file was left behind, so a reader can see one")
    assert lease.read(lease_file) is not None


# ---- the device's own identity -----------------------------------------------

def test_a_device_keeps_one_identity_across_restarts(tmp_path):
    first = lease.device_id(tmp_path)
    second = lease.device_id(tmp_path)

    assert first == second
    assert len(first) == 32


def test_the_identity_is_not_the_hostname_or_the_network(tmp_path):
    """Two machines can share a hostname, a hostname changes, and a MAC address
    is different per adapter and per VPN state. An identity that changes when
    the network does would make one machine look like several and break the
    lease exactly when it matters."""
    import platform
    import socket

    made = lease.device_id(tmp_path)

    assert socket.gethostname() not in made
    assert platform.node() not in made

    # The hostname IS kept, as a label — the owner has to recognise which of
    # his machines is holding the warehouse, and a bare uuid does not tell him.
    assert socket.gethostname() in lease.device_label(tmp_path)


def test_two_installations_on_one_machine_are_two_devices(tmp_path):
    """THE PROPERTY THAT ACTUALLY MATTERS, and the one the test above missed.

    Proved by mutation: replacing the random id with a hex-encoded hostname
    passed everything, because "the hostname is not literally in the string" is
    a weaker claim than "this identifies the installation".

    Two state directories are two installations — a reinstall, a second profile,
    a restored backup opened beside the original — and they must not both claim
    to be the same device, or one would silently renew the other's lease and
    both would be writing.
    """
    first = lease.device_id(tmp_path / "one")
    second = lease.device_id(tmp_path / "two")

    assert first != second, (
        "two installations share an identity, so each can renew the other's "
        "lease and both write at once")


def test_an_unreadable_identity_file_makes_a_new_one_rather_than_crashing(tmp_path):
    (tmp_path / "device.json").write_text("torn", encoding="utf-8")

    made = lease.device_id(tmp_path)

    assert len(made) == 32
    assert json.loads((tmp_path / "device.json").read_text(encoding="utf-8"))["device_id"] == made
