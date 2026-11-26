from dataclasses import asdict

from review.receipts import clear_pending_receipts, require_pending_show, save_pending_receipts
from review.reconcile import reconcile
from review.reports import get_close_receipt, store_report
from routing.shows import ApiError, control_write, mark_show_closed, require_open_show


def close(db, store_for, show_id, request_id):
    with control_write(db):
        prior = get_close_receipt(db, request_id)
        if prior is not None:
            if prior.show_id != show_id:
                raise ApiError(409, 'request_mismatch')
            return asdict(prior)

        require_pending_show(db, show_id, request_id)
        show = require_open_show(db, show_id)
        readiness = reconcile(db, store_for, show)
        if readiness.pending:
            save_pending_receipts(db, show_id, request_id, readiness.pending)
            return {'status': 'pending', 'show_id': show_id, 'pending': readiness.pending}

        receipt = store_report(db, show_id, request_id, readiness.playback)
        mark_show_closed(db, show_id)
        clear_pending_receipts(db, show_id)
        return asdict(receipt)
