"""Premium helpers (pure logic, no imports from main.py)."""

import time as _time


def grant_premium_entry(db, expiry_key, legacy_set_key, user_id, days):
    expiry = int(_time.time()) + (int(days) * 86400)
    db.hset(expiry_key, str(user_id), expiry)
    try:
        db.sadd(legacy_set_key, str(user_id))
    except Exception:
        pass
    return expiry


def revoke_premium_entry(db, expiry_key, legacy_set_key, user_id,
                         custom_tags_key=None, owner_id=None, is_admin_fn=None):
    """Revoke premium AND clean up any gift-card tag.

    Owner / admins keep their auto tags; everyone else loses the tag so an
    expired subscription can never leave a stale tag behind.
    """
    uid = str(user_id)
    try:
        db.hdel(expiry_key, uid)
    except Exception:
        pass
    try:
        db.srem(legacy_set_key, uid)
    except Exception:
        pass
    if custom_tags_key is not None:
        try:
            keep = False
            if owner_id is not None:
                try:
                    keep = int(user_id) == int(owner_id)
                except Exception:
                    keep = False
            if not keep and is_admin_fn is not None:
                try:
                    keep = bool(is_admin_fn(user_id))
                except Exception:
                    keep = False
            if not keep:
                db.hdel(custom_tags_key, uid)
        except Exception:
            pass


def is_premium_active(db, expiry_key, user_id):
    uid = str(user_id)
    try:
        if not db.hexists(expiry_key, uid):
            return False
        expiry = int(db.hget(expiry_key, uid) or 0)
    except Exception:
        return False
    return _time.time() < expiry


def remaining_seconds(db, expiry_key, user_id):
    try:
        expiry = int(db.hget(expiry_key, str(user_id)) or 0)
    except Exception:
        return 0
    return max(expiry - int(_time.time()), 0)
