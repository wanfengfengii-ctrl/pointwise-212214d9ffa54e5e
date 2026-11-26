from routing.shows import ApiError, get_show


def initialize_enrollment(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS enabled_seats (
            show_id TEXT NOT NULL REFERENCES shows(show_id),
            seat TEXT NOT NULL,
            position INTEGER NOT NULL,
            next_position INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (show_id, seat),
            UNIQUE (show_id, position)
        )
    ''')


def register_enabled_seats(db, show_id, seats):
    db.executemany(
        'INSERT INTO enabled_seats (show_id, seat, position) VALUES (?, ?, ?)',
        [(show_id, seat, position) for position, seat in enumerate(seats, 1)],
    )


def require_enabled_seat(db, show_id, seat):
    get_show(db, show_id)
    row = db.execute(
        'SELECT next_position FROM enabled_seats WHERE show_id = ? AND seat = ?',
        (show_id, seat),
    ).fetchone()
    if row is None:
        raise ApiError(404, 'seat_not_enabled')
    return row[0]


def list_enabled_seats(db, show_id):
    rows = db.execute('SELECT seat FROM enabled_seats WHERE show_id = ? ORDER BY position', (show_id,))
    return [row[0] for row in rows]
