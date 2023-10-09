# ---- Base ----
FROM python:3.11 AS base
ADD util /PittBOT/util
COPY bot.py /PittBOT/bot.py
COPY config.json /PittBOT/config.json
WORKDIR /PittBOT

# ---- Dependencies ----
FROM base as dependencies
COPY requirements.txt /PittBOT/requirements.txt
COPY welcome.png /PittBOT/welcome.png
RUN pip install -r requirements.txt

# ---- Release ----
FROM dependencies AS release
CMD [ "python", "bot.py" ]
