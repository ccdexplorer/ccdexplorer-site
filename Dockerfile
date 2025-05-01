FROM python:3.12
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt

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
COPY ./node_modules/flatpickr/dist/plugins/monthSelect/style.css /code/node_modules/flatpickr/dist/plugins/monthSelect/style.css
COPY ./node_modules/flatpickr/dist/plugins/monthSelect/index.js /code/node_modules/flatpickr/dist/plugins/monthSelect/index.js
COPY ./node_modules/flatpickr/dist/flatpickr.min.css /code/node_modules/flatpickr/dist/flatpickr.min.css


COPY ./node_modules/jquery/dist/jquery.min.js /code/node_modules/jquery/dist/jquery.min.js
COPY ./node_modules/htmx-ext-json-enc/json-enc.js /code/node_modules/htmx-ext-json-enc/json-enc.js
COPY ./node_modules/htmx-ext-class-tools/class-tools.js /code/node_modules/htmx-ext-class-tools/class-tools.js
COPY ./node_modules/microlight/microlight.js /code/node_modules/microlight/microlight.js
COPY ./node_modules/nouislider/dist/nouislider.js /code/node_modules/nouislider/dist/nouislider.js
COPY ./node_modules/nouislider/dist/nouislider.css /code/node_modules/nouislider/dist/nouislider.css

COPY ./node_modules/sortable-tablesort/sortable.min.css /code/node_modules/sortable-tablesort/sortable.min.css
COPY ./node_modules/sortable-tablesort/sortable.min.js /code/node_modules/sortable-tablesort/sortable.min.js

COPY ./node_modules/highlight.js/highlight.min.js /code/node_modules/highlight.js/highlight.min.js
COPY ./node_modules/highlight.js/styles/github-dark-dimmed.min.css /code/node_modules/highlight.js/styles/github-dark-dimmed.min.css
COPY ./node_modules/highlight.js/languages/rust.min.js /code/node_modules/highlight.js/languages/rust.min.js
COPY ./node_modules/highlight.js/languages/json.min.js /code/node_modules/highlight.js/languages/json.min.js

COPY ./node_modules/tabulator-tables/dist/js/tabulator.min.js /code/node_modules/tabulator-tables/dist/js/tabulator.min.js
COPY ./node_modules/tabulator-tables/dist/css/tabulator.min.css /code/node_modules/tabulator-tables/dist/css/tabulator.min.css
COPY ./node_modules/tabulator-tables/dist/css/tabulator_bootstrap5.min.css /code/node_modules/tabulator-tables/dist/css/tabulator_bootstrap5.min.css


COPY ./addresses/mainnet_addresses_to_indexes.pickle /code/addresses/mainnet_addresses_to_indexes.pickle
COPY ./addresses/testnet_addresses_to_indexes.pickle /code/addresses/testnet_addresses_to_indexes.pickle

CMD ["uvicorn", "app.main:app",  "--log-level", "warning", "--proxy-headers", "--host", "0.0.0.0", "--port", "80", "--workers", "2"]
