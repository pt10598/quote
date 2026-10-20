release: python init_db.py
web: gunicorn app:application --workers 1 --threads 4 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile -
