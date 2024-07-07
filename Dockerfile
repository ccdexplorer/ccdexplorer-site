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

# download concordium-client package
RUN wget https://distribution.concordium.software/tools/linux/concordium-client_6.3.0-1 -O /code/concordium-client && chmod +x /code/concordium-client

# download rustup install script
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > /code/rustup.sh && chmod +x /code/rustup.sh

# install rustup
RUN /code/rustup.sh -y
RUN rm /code/rustup.sh

# add rust to path
ENV PATH="/root/.cargo/bin:${PATH}"

# install cargo-concordium
RUN cargo install cargo-concordium

CMD ["uvicorn", "app.main:app",  "--log-level", "info", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
