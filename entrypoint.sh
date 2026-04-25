#!/bin/sh

echo "Aplicăm migrările..."
python manage.py migrate --noinput

echo "Colectăm fișierele statice..."
python manage.py collectstatic --noinput

echo "Pornim serverul Django..."
exec python manage.py runserver 0.0.0.0:8000