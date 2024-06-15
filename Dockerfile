FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11
# 
WORKDIR /code

# 
COPY ./requirements.txt /code/requirements.txt

# 
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 
COPY ./app /code/app
COPY ./app/templates/ /code/app/templates/
COPY ./app/templates/tmp /code/app/templates/tmp
COPY ./app/static/ /code/app/static/

CMD ["uvicorn", "app.main:app",  "--log-level", "info", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
