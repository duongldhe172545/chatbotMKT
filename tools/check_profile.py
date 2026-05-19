"""Show full latest dealer_profile_raw + session state."""
from __future__ import annotations

import json
import sqlite3
import sys

con = sqlite3.connect("data/chatbot.db")
con.row_factory = sqlite3.Row

# Session
row = con.execute("SELECT session_id, turn_count, current_slot, stage FROM sessions LIMIT 1").fetchone()
if not row:
    print("No session")
    sys.exit(0)
print(f"=== Session {row['session_id'][:8]} ===")
print(f"turn={row['turn_count']} slot={row['current_slot']} stage={row['stage']}")

# Profile
row = con.execute("SELECT * FROM dealer_profile_raw LIMIT 1").fetchone()
d = dict(row)
print("\n=== Profile ===")
fields = [
    "owner_name", "dealer_name", "address", "province", "district",
    "phone_or_zalo", "main_product", "main_category", "category_stack",
    "business_model_signal", "est_team_size", "supplier_brands",
    "primary_contact_channel", "facebook",
    "customer_old_percentage", "customer_storage_method",
    "customer_pain", "payment_terms_signal", "warranty_responsibility_signal",
    "brandkit_consent", "color_accent",
    "brand_name_short", "initials_full", "initial_single",
    "contact_name", "contact_role", "hotline",
    "slogan_options",
]
for k in fields:
    v = d.get(k)
    if k in ("category_stack", "supplier_brands", "slogan_options") and isinstance(v, str):
        v = json.loads(v) if v else []
    print(f"  {k}: {v!r}")

con.close()
