# FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11
FROM python:3.12
# 
# # The installer requires curl (and certificates) to download the release archive
# RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# # Download the latest installer
# ADD https://astral.sh/uv/install.sh /uv-installer.sh

# # Run the installer then remove it
# RUN sh /uv-installer.sh && rm /uv-installer.sh

# # Ensure the installed binary is on the `PATH`
# ENV PATH="/root/.cargo/bin/:$PATH"

WORKDIR /code

# # 
# COPY ./requirements.txt /code/requirements.txt

# # --system is needed, otherwise error on missing venv
# RUN uv pip install --system -r requirements.txt
# # RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt




# download concordium-client package
RUN wget https://distribution.concordium.software/tools/linux/concordium-client_7.0.1-0 -O /code/concordium-client && chmod +x /code/concordium-client

# download rustup install script
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > /code/rustup.sh && chmod +x /code/rustup.sh

# install rustup
RUN /code/rustup.sh -y
RUN rm /code/rustup.sh

# add rust to path
ENV PATH="/root/.cargo/bin:${PATH}"

# install cargo-concordium
RUN cargo install cargo-concordium


WORKDIR /code

# 
COPY ./requirements.txt /code/requirements.txt

# 
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app
COPY ./app/templates/ /code/app/templates/
COPY ./app/static/ /code/app/static/
COPY ./custom_scss /code/custom_scss
COPY ./node_modules/bootstrap-icons/font/bootstrap-icons.min.css /code/node_modules/bootstrap-icons/font/bootstrap-icons.min.css
COPY ./node_modules/bootstrap-icons/font/fonts /code/node_modules/bootstrap-icons/font/fonts
COPY ./node_modules/bootstrap/dist/js/bootstrap.bundle.min.js /code/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js
COPY ./node_modules/plotly.js-dist/plotly.js /code/node_modules/plotly.js-dist/plotly.js
COPY ./node_modules/plotly.js-strict-dist-min/plotly-strict.min.js /code/node_modules/plotly.js-strict-dist-min/plotly-strict.min.js
COPY ./node_modules/htmx.org/dist/htmx.js /code/node_modules/htmx.org/dist/htmx.js
COPY ./node_modules/flatpickr/dist/flatpickr.min.js /code/node_modules/flatpickr/dist/flatpickr.min.js
COPY ./node_modules/flatpickr/dist/flatpickr.min.css /code/node_modules/flatpickr/dist/flatpickr.min.css
COPY ./node_modules/jquery/dist/jquery.min.js /code/node_modules/jquery/dist/jquery.min.js
COPY ./node_modules/htmx-ext-json-enc/json-enc.js /code/node_modules/htmx-ext-json-enc/json-enc.js
COPY ./node_modules/htmx-ext-class-tools/class-tools.js /code/node_modules/htmx-ext-class-tools/class-tools.js

COPY ./node_modules/sortable-tablesort/sortable.min.css /code/node_modules/sortable-tablesort/sortable.min.css
COPY ./node_modules/sortable-tablesort/sortable.min.js /code/node_modules/sortable-tablesort/sortable.min.js

COPY ./node_modules/hightlight.js/styles/atom-one-dark.css /code/node_modules/hightlight.js/styles/atom-one-dark.css
COPY ./node_modules/hightlight.js/styles/atom-one-dark.css /code/node_modules/hightlight.js/styles/atom-one-dark.css


COPY ./addresses/mainnet_addresses_to_indexes.pickle /code/addresses/mainnet_addresses_to_indexes.pickle
COPY ./addresses/testnet_addresses_to_indexes.pickle /code/addresses/testnet_addresses_to_indexes.pickle

CMD ["uvicorn", "app.main:app",  "--log-level", "warning", "--proxy-headers", "--host", "0.0.0.0", "--port", "80", "--workers", "2"]
