# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError

GROUP_ADMIN = 'furniture_marketplace.group_marketplace_admin'
GROUP_MANAGER = 'furniture_marketplace.group_marketplace_manager'
GROUP_MANUFACTURER = 'furniture_marketplace.group_manufacturer_portal'


def check_marketplace_manager(env):
    """Server-side guard for approval workflows (not only hidden buttons)."""
    if not env.user.has_group(GROUP_MANAGER):
        raise AccessError(env._('Only Marketplace Managers or Administrators can perform this action.'))


def is_manufacturer_portal_user(env):
    user = env.user
    return bool(user.share and user.has_group(GROUP_MANUFACTURER)
                and not user.has_group(GROUP_MANAGER))


def split_category_path(path):
    """'Dining / Tables' or 'Dining > Tables' -> ['Dining', 'Tables'].

    Never returns an empty list, so callers can always take the leaf or the
    first element safely (a value such as '///' used to crash the import).
    """
    parts = [p.strip() for p in (path or '').replace('>', '/').split('/') if p.strip()]
    return parts or ['Other']
