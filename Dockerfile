# use a node base image
FROM python

COPY . /PittBOT
WORKDIR /PittBOT

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "bot.py" ]
