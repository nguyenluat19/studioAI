"""Atomic credit accounting. All balance changes are single guarded UPDATEs."""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import CreditAdjustment, CreditLedgerEntry, GenerationHistory, Transaction, User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_ledger(db: Session, user_id: int, kind: str, amount: float, reason: str,
                   ref_type: str = "", ref_id: int | str | None = None) -> None:
    bal = db.scalar(select(User.credits_balance).where(User.id == user_id))
    row = CreditLedgerEntry(user_id=user_id, kind=kind, amount=round(float(amount), 2),
                           balance_after=round(float(bal or 0), 2), reason=(reason or "")[:2000],
                           ref_type=ref_type, ref_id=str(ref_id or ""))
    db.add(row)



def charge(db: Session, user_id: int, cost: float, *, kind: str = "spend",
           reason: str = "Chi tiêu credit", ref_type: str = "", ref_id: int | str | None = None) -> bool:
    """Deduct `cost` iff balance suffices. Returns False when credits are insufficient."""
    if cost <= 0:
        return True
    res = db.execute(
        update(User)
        .where(User.id == user_id, User.credits_balance >= cost)
        .values(credits_balance=User.credits_balance - cost)
    )
    if res.rowcount != 1:
        return False
    _record_ledger(db, user_id, kind, -float(cost), reason, ref_type, ref_id)
    return True


def add_credits(db: Session, user_id: int, amount: float, *, kind: str = "topup",
                reason: str = "Cộng credit", ref_type: str = "", ref_id: int | str | None = None) -> None:
    if amount == 0:
        return
    db.execute(update(User).where(User.id == user_id)
               .values(credits_balance=User.credits_balance + amount))
    _record_ledger(db, user_id, kind, float(amount), reason, ref_type, ref_id)


def adjust(db: Session, user_id: int, amount: float, admin_id: int | None, reason: str = "") -> float | None:
    """Admin +/- credits. One guarded UPDATE so concurrent deductions can never push the balance below zero.
    Returns the new balance, or None when a deduction would make it negative (nothing changed)."""
    res = db.execute(update(User).where(User.id == user_id, User.credits_balance + amount >= 0)
                     .values(credits_balance=User.credits_balance + amount))
    if res.rowcount != 1:
        db.rollback()
        return None
    bal = round(db.scalar(select(User.credits_balance).where(User.id == user_id)), 2)
    db.add(CreditAdjustment(user_id=user_id, admin_id=admin_id, amount=amount, balance_after=bal,
                            reason=reason.strip()[:200]))
    _record_ledger(db, user_id, "adjustment", float(amount), reason or "Điều chỉnh credit", "admin", admin_id)
    db.commit()
    return bal


def mark_processing(db: Session, gen_id: int) -> bool:
    res = db.execute(update(GenerationHistory)
                     .where(GenerationHistory.id == gen_id, GenerationHistory.status == "pending")
                     .values(status="processing", updated_at=_now()))
    db.commit()
    return res.rowcount == 1


def touch(db: Session, gen_id: int) -> None:
    """Heartbeat: tell the reaper this job is alive and make progress."""
    db.execute(update(GenerationHistory)
               .where(GenerationHistory.id == gen_id, GenerationHistory.status == "processing")
               .values(updated_at=_now()))
    db.commit()


def mark_success(db: Session, gen_id: int, output_url: str) -> None:
    db.execute(update(GenerationHistory)
               .where(GenerationHistory.id == gen_id, GenerationHistory.status == "processing")
               .values(status="success", output_video_url=output_url, error_message="",
                       updated_at=_now()))
    db.commit()


def fail_and_refund(db: Session, gen_id: int, message: str) -> bool:
    """Mark a generation failed and refund exactly what was charged — at most once.

    The status guard makes this idempotent: a retry or a double failure callback
    cannot refund twice.
    """
    gen = db.get(GenerationHistory, gen_id)
    if gen is None:
        return False
    res = db.execute(
        update(GenerationHistory)
        .where(GenerationHistory.id == gen_id, GenerationHistory.status.in_(("pending", "processing")))
        .values(status="failed", error_message=message[:2000], updated_at=_now())
    )
    if res.rowcount != 1:
        db.rollback()
        return False
    add_credits(db, gen.user_id, gen.credits_cost, kind="refund", reason=message or "Hoàn credit", ref_type="generation", ref_id=gen_id)
    db.commit()
    return True


def settle_topup(db: Session, tx_id: int, allow_from: tuple[str, ...] = ("pending",)) -> bool:
    """pending (or an explicitly allowed state) -> success and credit the wallet, exactly once."""
    tx = db.get(Transaction, tx_id)
    if tx is None:
        return False
    res = db.execute(update(Transaction)
                     .where(Transaction.id == tx_id, Transaction.status.in_(allow_from))
                     .values(status="success"))
    if res.rowcount != 1:
        db.rollback()
        return False
    add_credits(db, tx.user_id, tx.credits_added, kind="topup",
                reason=f"Nạp {int(tx.amount_vnd):,}đ ({tx.transaction_code})", ref_type="transaction", ref_id=tx_id)
    db.commit()
    return True
