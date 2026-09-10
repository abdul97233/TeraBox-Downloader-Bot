"""Tag helpers (pure logic, no imports from main.py).

All functions take an explicit ``db`` handle so they can be unit-tested
and reused from any handler module without circular imports.
"""


def get_tag_entry(db, custom_tags_key, user_id):
    try:
        return db.hget(custom_tags_key, str(user_id)) or ""
    except Exception:
        return ""


def set_tag_entry(db, custom_tags_key, user_id, tag):
    db.hset(custom_tags_key, str(user_id), tag)


def clear_tag_entry(db, custom_tags_key, user_id):
    try:
        db.hdel(custom_tags_key, str(user_id))
    except Exception:
        pass


def resolve_custom_tag(db, custom_tags_key, user_id, *, owner_id,
                       is_admin_fn, is_premium_fn):
    """Return the effective tag for a user.

    - OWNER_ID always resolves to OWNER (persisted).
    - Admins always resolve to ADMIN (persisted).
    - Regular users whose premium has expired get their gift-card tag
      REMOVED from Redis and resolve to "".
    """
    uid = str(user_id)
    try:
        uid_int = int(user_id)
    except Exception:
        uid_int = None

    if uid_int is not None and uid_int == int(owner_id):
        tag = get_tag_entry(db, custom_tags_key, uid) or "OWNER"
        set_tag_entry(db, custom_tags_key, uid, tag)
        return tag

    try:
        if is_admin_fn(user_id):
            tag = get_tag_entry(db, custom_tags_key, uid) or "ADMIN"
            set_tag_entry(db, custom_tags_key, uid, tag)
            return tag
    except Exception:
        pass

    try:
        if not is_premium_fn(user_id):
            clear_tag_entry(db, custom_tags_key, uid)
            return ""
    except Exception:
        pass

    return get_tag_entry(db, custom_tags_key, uid)
