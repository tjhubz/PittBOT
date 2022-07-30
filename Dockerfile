# ---- Base ----
FROM python AS base
COPY . ../PittBOT
WORKDIR /PittBOT

# ---- Dependencies ----
FROM base as dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ---- Release ----
FROM dependencies AS release
CMD [ "python", "bot.py" ]
