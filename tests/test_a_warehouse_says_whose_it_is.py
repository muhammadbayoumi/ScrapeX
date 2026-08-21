"""A warehouse records the account it belongs to.

WHY THIS FILE EXISTS. He ruled that a database belongs to one account and not to
everyone on the machine — «لكل حساب قاعدة بيانات» (`REQ-26`) — and then settled the
one question that could not be answered from the code by naming an address: «ايضا
databse الموجودة حاليا اجعلها تخص حساب muhammad.bayoumi.ali@gmail.com». That is
`Q-14` answered: **the account is the signed-in address**, which matters because it
decides where other people's data lands.

WHAT IS DELIBERATELY NOT TESTED HERE, because it is not built: refusing to open a
warehouse claimed by someone else. `DATABASE_ROOT` is still `~/.scrapex`, one
directory per operating-system user, so a second account has nowhere else to go and
enforcing the rule now would refuse the only warehouse there is. `assert_owner`
exists so the rule has ONE definition when `REQ-26`'s layout arrives; the tests below
cover the claim, not an enforcement that would lock him out.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import account
from scrapex.databases import DatabaseRegistry, EngineDatabase

HIS = "muhammad.bayoumi.ali@gmail.com"
OTHER = "someone.else@gmail.com"


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def test_a_fresh_warehouse_belongs_to_nobody(conn):
    """`None` is a real answer, not a failure: every warehouse that predates this is
    unclaimed, and `R-23` calls an empty installation the normal first run."""
    assert account.owner(conn) is None


def test_claiming_records_the_address_and_reads_back(conn):
    account.claim(conn, HIS)

    assert account.owner(conn) == HIS


def test_the_same_account_twice_is_a_no_op_and_not_an_error(conn):
    """Re-running setup must not be a failure mode."""
    account.claim(conn, HIS)
    assert account.claim(conn, HIS) == HIS
    assert account.owner(conn) == HIS


def test_a_different_account_is_refused_rather_than_overwritten(conn):
    """Handing a warehouse from one account to another MOVES SOMEONE'S DATA under
    another name. `R-24`'s reasoning about a user's database applied to its owner:
    deliberately, never behind his back."""
    account.claim(conn, HIS)

    with pytest.raises(account.AccountMismatch) as raised:
        account.claim(conn, OTHER)

    assert HIS in str(raised.value) and OTHER in str(raised.value)
    assert account.owner(conn) == HIS, "the refusal must not have changed anything"


def test_force_re_points_it_when_that_really_is_the_intent(conn):
    account.claim(conn, HIS)

    assert account.claim(conn, OTHER, force=True) == OTHER
    assert account.owner(conn) == OTHER


def test_an_empty_account_is_refused(conn):
    """An empty owner is worse than no owner: it reads as claimed and names nobody."""
    with pytest.raises(ValueError):
        account.claim(conn, "   ")

    assert account.owner(conn) is None


def test_surrounding_space_is_not_part_of_the_address(conn):
    """A pasted address carries whitespace, and " a@b.com" must not become a second
    account distinct from "a@b.com"."""
    account.claim(conn, f"  {HIS}  ")

    assert account.owner(conn) == HIS


def test_the_local_part_keeps_its_case(conn):
    """Email local parts are case-sensitive by specification, even though almost
    nobody treats them so. Folding them would quietly merge two addresses a provider
    considers different — and this decides whose data is whose, so it is not the
    place to be helpful."""
    account.claim(conn, "Muhammad.Bayoumi@example.com")

    assert account.owner(conn) == "Muhammad.Bayoumi@example.com"


def test_assert_owner_names_both_sides(conn):
    """The rule has one definition, ready for the per-account layout."""
    account.claim(conn, HIS)

    account.assert_owner(conn, HIS)          # the owner passes silently
    with pytest.raises(account.AccountMismatch):
        account.assert_owner(conn, OTHER)


def test_an_unclaimed_warehouse_passes_any_account(conn):
    """Every warehouse in existence before this is unclaimed, and none of them may
    stop working because a rule arrived after them."""
    account.assert_owner(conn, HIS)
    account.assert_owner(conn, OTHER)
