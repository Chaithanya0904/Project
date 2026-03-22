import sqlite3

AUTO_RESOLUTIONS = {
    "broken streetlight": {"resolution": "Maintenance assigned. 48h repair.", "status": "in_progress"},
    "damaged footpath sidewalk": {"resolution": "Schedules by Civil Works.", "status": "in_progress"},
    "flood": {"resolution": "Emergency Drainage team dispatched.", "status": "in_progress"},
    "garbage": {"resolution": "Sanitation truck scheduled.", "status": "resolved"},
    "open manhole": {"resolution": "Urgent safety barrier and replacement.", "status": "in_progress"},
    "sewageleak": {"resolution": "Sewerage Board notified.", "status": "in_progress"},
    "waterleakage": {"resolution": "Pipeline repair team notified.", "status": "in_progress"}
}

def auto_process_complaint(complaint_id, result_text, get_db_fn):
    if not result_text or result_text == "No object detected": return
    issue = result_text.split(',')[0].strip().lower()
    if issue in AUTO_RESOLUTIONS:
        cfg = AUTO_RESOLUTIONS[issue]
        conn = get_db_fn()
        conn.execute("UPDATE complients SET result = ?, status = ? WHERE id = ?", (cfg['resolution'], cfg['status'], complaint_id))
        conn.commit()
        conn.close()
