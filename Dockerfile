# ---- Base ----
FROM python AS base
ADD util /PittBOT/util
COPY bot.by /PittBOT/bot.py
COPY config.json /PittBOT/config.json
WORKDIR /PittBOT

# ---- Dependencies ----
FROM base as dependencies
COPY requirements.txt /PittBOT/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---- Release ----
FROM dependencies AS release
CMD [ "python", "bot.py" ]
