import time

_sessions = {}


def get_session(user_id):

    if user_id not in _sessions:

        _sessions[user_id] = {
            "created_at": time.time(),
            "history": []
        }

    return _sessions[user_id]


def update_session(user_id, data):

    if user_id not in _sessions:

        get_session(user_id)

    _sessions[user_id]["history"].append(data)