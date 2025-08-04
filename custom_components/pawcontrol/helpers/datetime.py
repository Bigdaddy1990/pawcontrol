from datetime import datetime

def is_today(date_obj):
    return date_obj.date() == datetime.today().date()
