from datetime import datetime
from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": dt.strftime("%B %Y"),
    }


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    sql = "SELECT amount, category FROM expenses WHERE user_id = ?"
    params = [user_id]
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return {"total_spent": "₹0.00", "transaction_count": 0, "top_category": "—"}
    total = sum(r["amount"] for r in rows)
    category_totals = {}
    for r in rows:
        category_totals[r["category"]] = category_totals.get(r["category"], 0) + r["amount"]
    top_category = max(category_totals, key=category_totals.get)
    return {
        "total_spent": f"₹{total:,.2f}",
        "transaction_count": len(rows),
        "top_category": top_category,
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    sql = (
        "SELECT id, date, description, category, amount FROM expenses"
        " WHERE user_id = ?"
    )
    params = [user_id]
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        result.append({
            "id": r["id"],
            "date": dt.strftime("%d %b %Y"),
            "description": r["description"],
            "category": r["category"],
            "amount": f"₹{r['amount']:,.2f}",
        })
    return result


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    sql = (
        "SELECT category, SUM(amount) as total FROM expenses"
        " WHERE user_id = ?"
    )
    params = [user_id]
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    sql += " GROUP BY category ORDER BY total DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return []
    grand_total = sum(r["total"] for r in rows)
    breakdown = [
        {
            "name": r["category"],
            "amount": f"₹{r['total']:,.2f}",
            "pct": round(r["total"] / grand_total * 100) if grand_total else 0,
        }
        for r in rows
    ]
    pct_sum = sum(item["pct"] for item in breakdown)
    if pct_sum != 100 and breakdown:
        breakdown[0]["pct"] += 100 - pct_sum
    return breakdown
