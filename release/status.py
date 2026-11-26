from dataclasses import asdict

from release.amendments import get_amendment, list_show_amendments
from routing.shows import ApiError


def project_amendment(order):
    projection = asdict(order)
    projection['seats'] = {}
    for seat, state in order.seats.items():
        result = state['evidence']
        if result is None:
            result = {'status': 'pending', 'original_seq': None, 'amendment_seq': None}
        projection['seats'][seat] = {**result, 'play_token': state['play_token']}
    return projection


def amend_status(db, show_id, amendment_id):
    order = get_amendment(db, show_id, amendment_id)
    if order is None:
        raise ApiError(404, 'unknown_amendment')
    return project_amendment(order)


def list_show_amendment_status(db, show_id):
    return [project_amendment(order) for order in list_show_amendments(db, show_id)]
