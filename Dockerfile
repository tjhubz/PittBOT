# ---- Base ----
FROM python AS base


# ---- Dependencies ----
FROM base as dependencies
COPY requirements.txt ../PittBOT
RUN pip install --no-cache-dir -r requirements.txt

# ---- Release ----
FROM dependencies AS release
WORKDIR /PittBOT
COPY . .
CMD [ "python", "bot.py" ]
